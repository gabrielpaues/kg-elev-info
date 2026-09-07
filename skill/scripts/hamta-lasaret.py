#!/usr/bin/env python3
"""Hämtar skolans läsårsdatum och skriver data/lasaret-datum.md.
Robust mot terminsskifte: hittar ALLA sektioner "(Höst|Vår)terminen ÅÅÅÅ" oavsett ordning
eller om en termin försvunnit från sidan. Kör vid varje skillkörning (ersätter gamla sed-kommandot).
"""
import html as H
import re
import subprocess
import sys
import datetime

URL = "https://kungsholmensgymnasium.stockholm/viktiga-datum-under-lasaret/"
UT = sys.argv[1] if len(sys.argv) > 1 else None

raw = subprocess.run(["curl", "-sL", "--max-time", "30", "-A", "Mozilla/5.0", URL],
                     capture_output=True, text=True, timeout=45).stdout
raw = re.sub(r"<script.*?</script>", "", raw, flags=re.S)
raw = re.sub(r"<style.*?</style>", "", raw, flags=re.S)
text = H.unescape(re.sub(r"<[^>]+>", "\n", raw))
lines = [l.strip() for l in text.splitlines() if l.strip()]

# huvudinnehållet: från "Läsåret är indelat" till "Mer inom" (sidfot)
start = next((i for i, l in enumerate(lines) if "Läsåret är indelat" in l), 0)
stop = next((i for i, l in enumerate(lines) if l.startswith("Mer inom")), len(lines))
kropp = lines[start:stop]

# terminsektioner: rubrik "(Höst|Vår)terminen ÅÅÅÅ" följd av datarader tills nästa rubrik
sektioner = []
aktuell = None
for l in kropp:
    if re.match(r"^(Höst|Vår)terminen \d{4}", l):
        aktuell = {"rubrik": l, "rader": []}
        sektioner.append(aktuell)
    elif aktuell is not None and not l.startswith(("Uppdaterad", "Mer information")):
        aktuell["rader"].append(l)
    elif l.startswith("Uppdaterad"):
        aktuell = None

hämtad = datetime.date.today().isoformat()
md = [f"# Kungsholmens gymnasium — viktiga datum",
      f"Källa: {URL}",
      f"Hämtad: {hämtad} (uppdateras automatiskt av skillen vid varje körning)", ""]
for s in sektioner:
    md.append(f"## {s['rubrik']}")
    md += [f"- {r}" for r in s["rader"]]
    md.append("")

md += ["## Kontakter (från skolans e-tjänstesida)",
       "- Support elever: 020-33 09 00, elevsupport@edu.stockholm.se (alla dagar 07–22)",
       "- Support vårdnadshavare: 08-508 11 552, support.vardnadshavare@stockholm.se (mån–tor 08–16.30, fre 08–16)"]

if not sektioner:
    print("VARNING: inga terminsektioner hittades — sidans struktur kan ha ändrats", file=sys.stderr)
    sys.exit(1)

ut = "\n".join(md)
if UT:
    open(UT, "w", encoding="utf-8").write(ut + "\n")
    print(f"skrev {UT} ({len(sektioner)} terminer, {sum(len(s['rader']) for s in sektioner)} rader)")
else:
    print(ut)
