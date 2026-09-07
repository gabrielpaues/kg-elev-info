#!/usr/bin/env python3
"""Parsar https://kungsholmensgymnasium.stockholm/konserter/ till strukturerad JSON.
Användning: konserter.py [htmlfil]  (utan arg: hämtar live)
Filtrera på klass med: konserter.py --klass <KLASS> --ak <ÅK>
Årskurs härleds ur klasskod: t.ex. Ab26cd → antagen 2026 → åk 1 läsåret 2026/2027.
"""
import json
import re
import sys
import html as H
import urllib.request

URL = "https://kungsholmensgymnasium.stockholm/konserter/"
klass_arg = None
ak_arg = None
args = sys.argv[1:]
if "--klass" in args:
    klass_arg = args[args.index("--klass") + 1]
if "--ak" in args:
    ak_arg = int(args[args.index("--ak") + 1])
src = [a for a in args if not a.startswith("--") and a not in (klass_arg, str(ak_arg))]

if src:
    raw = open(src[0], encoding="utf-8", errors="ignore").read()
else:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="ignore")

raw = re.sub(r"<script.*?</script>", "", raw, flags=re.S)
raw = re.sub(r"<style.*?</style>", "", raw, flags=re.S)

# Splitta på h3-rubriker (varje konsert = ett block tills nästa h3/h2-slut)
blocks = []
for m in re.finditer(r"<h3[^>]*>(.*?)</h3>(.*?)(?=<h3[^>]*>|<h2[^>]*>Mer inom|$)", raw, re.S):
    titel = H.unescape(re.sub(r"<[^>]+>", "", m.group(1))).replace("\xa0", " ").strip()
    kropp = H.unescape(re.sub(r"<[^>]+>", "\n", m.group(2)))
    rader = [r.strip() for r in kropp.splitlines() if r.strip()]
    text = "\n".join(rader)

    tid = re.search(r"Tid:\s*(.+)", text)
    plats = re.search(r"Plats:\s*(.+)", text)
    medverkande = re.search(r"Medverkande:\s*(.+?)(?:\n(?:Information|Biljett|Boka|Samtliga|Fri entré)|$)", text, re.S)
    biljett = None
    for pat in (r"(Biljettsläpp[^.\n]*(?:\.[^.\n]*)?)", r"(Biljetter[^.\n]*(?:\.[^.\n]*)?)", r"(Fri entré)", r"(Samtliga biljetter[^.\n]*)", r"(Information om biljetter[^.\n]*)"):
        b = re.search(pat, text)
        if b:
            biljett = b.group(1).strip()
            break

    klasser = sorted(set(re.findall(r"\b[NS][a-z]\d{2}[a-z]{2}\b", medverkande.group(1) if medverkande else "")))

    blocks.append({
        "titel": titel,
        "tid": tid.group(1).strip() if tid else None,
        "plats": plats.group(1).strip() if plats else None,
        "medverkande_text": (medverkande.group(1).replace("\n", " ").strip() if medverkande else None),
        "klasser": klasser,
        "biljett": biljett,
    })

# antal h3-hittade
fallback = len(blocks) == 0

if klass_arg:
    # härled årskurs: 26 → åk 1 om läsårsstart 2026, även "hela årskurs N" / "Hela skolan"
    m = re.match(r"[NS][a-z](\d{2})[a-z]{2}", klass_arg)
    antaget = 2000 + int(m.group(1)) if m else None
    import datetime
    ak = ak_arg or (datetime.date.today().year + (1 if datetime.date.today().month >= 7 else 0) - antaget if antaget else None)
    träffar = []
    for b in blocks:
        if klass_arg in b["klasser"]:
            b["match_anledning"] = f"klass {klass_arg} utsedd"; träffar.append(b); continue
        mt = b["medverkande_text"] or ""
        if ak and re.search(rf"(hela årskurs {ak}|årskurs {ak}\b)", mt, re.I):
            b["match_anledning"] = f"hela årskurs {ak}"; träffar.append(b); continue
        # "hela skolan" gäller bara om ingen specifik grupp (klasskod eller annan årskurs) nämns
        specifik = b["klasser"] or re.search(r"årskurs \d", mt, re.I)
        if not specifik and re.search(r"(Hela Kungsholmens gymnasium|Stockholms musikgymnasium/Kungsholmens gymnasium|Kungsholmens gymnasium/Stockholms musikgymnasium)", mt, re.I):
            b["match_anledning"] = "hela skolan"; träffar.append(b); continue
    print(json.dumps({"källa": URL, "klass": klass_arg, "årskurs": ak, "antal_totalt": len(blocks), "konserter": träffar}, ensure_ascii=False, indent=2))
else:
    print(json.dumps({"källa": URL, "antal_totalt": len(blocks), "konserter": blocks}, ensure_ascii=False, indent=2))
