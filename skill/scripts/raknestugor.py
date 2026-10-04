#!/usr/bin/env python3
"""Parsar Mattecentrums räknestugor (Stockholm) till strukturerad JSON.

Användning:
  raknestugor.py                  — filtrera på RAKNESTUGOR_PLATSER ur data/elev.local
  raknestugor.py --list           — lista alla platser på sidan (för val vid första körningen)
  raknestugor.py --platser "A, B" — filtrera på angivna platser (utan elev.local)
  raknestugor.py [htmlfil]        — parsa sparad HTML i stället för att hämta live

Platsnamn matchas skiftlägesokänsligt: exakt eller in-under-sträng är säker träff;
nära stavning (difflib) rapporteras som osäker träff i stället för att tysta avfärdas.
Källa: https://www.mattecentrum.se/raknestugor/stockholm
"""
import datetime
import difflib
import html as H
import json
import re
import subprocess
import sys
from pathlib import Path

URL = "https://www.mattecentrum.se/raknestugor/stockholm"
args = sys.argv[1:]

list_mode = "--list" in args
platser_arg = None
config_path = Path(__file__).resolve().parents[2] / "data" / "elev.local"
if "--platser" in args:
    platser_arg = [p.strip() for p in args[args.index("--platser") + 1].split(",") if p.strip()]
if "--config" in args:
    config_path = Path(args[args.index("--config") + 1])
src = [a for a in args if not a.startswith("--")]

if src:
    raw = open(src[0], encoding="utf-8", errors="ignore").read()
else:
    raw = subprocess.run(["curl", "-sL", "--max-time", "30", "-A", "Mozilla/5.0", URL],
                         capture_output=True, text=True, timeout=45).stdout
raw = re.sub(r"<script.*?</script>", "", raw, flags=re.S)
raw = re.sub(r"<style.*?</style>", "", raw, flags=re.S)

# notiser (stängd/uppehåll) ur introt före platslistan; split på meningspunkt
# men "v.44" överlever (punkten följs av siffra, inte blanksteg)
delar = raw.split('<nav class="tutoring-locations">', 1)
intro_text = H.unescape(re.sub(r"<[^>]+>", " ", delar[0]))
notiser = sorted({(" ".join(m.split())).rstrip(".") + "." for m in re.split(r"\.\s+", intro_text)
                  if "stäng" in m.lower() and len(m.strip()) < 200})

# platserna: <a href="/raknestugor/..."> <h2>namn</h2> <span>adress</span>
#            <h3><span>dag</span><span>tid</span></h3> ... </a>
alla = []
for m in re.finditer(r'<a href="(/raknestugor/[^"]+)">(.*?)</a>', raw, re.S):
    block = m.group(2)
    plats_m = re.search(r"<h2[^>]*>(.*?)</h2>", block, re.S)
    if not plats_m:
        continue
    namn = " ".join(H.unescape(plats_m.group(1)).split())
    adress_m = re.search(r"</h2>\s*<span[^>]*>(.*?)</span>", block, re.S)
    tider = []
    for t in re.finditer(r"<h3[^>]*>\s*<span[^>]*>(.*?)</span>\s*<span[^>]*>(.*?)</span>", block, re.S):
        dag = " ".join(H.unescape(t.group(1)).split())
        tid = " ".join(H.unescape(t.group(2)).split()).replace(" ", "")
        tider.append({"dag": dag, "tid": tid})
    alla.append({"plats": namn,
                 "adress": " ".join(H.unescape(adress_m.group(1)).split()) if adress_m else None,
                 "url": "https://www.mattecentrum.se" + m.group(1), "tider": tider})

if list_mode:
    print(json.dumps({"källa": URL, "antal": len(alla), "alla_platser": alla},
                     ensure_ascii=False, indent=1))
    sys.exit(0)

def ladda_config():
    """Returnerar (raknestugor, platser) ur elev.local; (None, None) om filen/nycklarna saknas."""
    if not config_path.is_file():
        return None, None
    kv = {}
    for rad in config_path.read_text(encoding="utf-8").splitlines():
        if "=" in rad and not rad.strip().startswith("#"):
            k, _, v = rad.partition("=")
            kv[k.strip()] = v.strip()
    v = kv.get("RAKNESTUGOR", "").lower()
    raknestugor = v == "true" if v in ("true", "false") else None
    platser = [p.strip() for p in kv.get("RAKNESTUGOR_PLATSER", "").split(",") if p.strip()]
    return raknestugor, (platser or None)

raknestugor_cfg, platser_cfg = ladda_config()
if platser_arg is not None:
    platser_cfg = platser_arg
    raknestugor_cfg = True

saknade, osakra = [], []
if platser_cfg:
    träffar = []
    for namn_cfg in platser_cfg:
        stark = None
        svaga = []
        for plats in alla:
            a, b = namn_cfg.casefold(), plats["plats"].casefold()
            if a == b:
                stark = dict(plats, match="exakt"); break
            if a in b or b in a:
                stark = dict(plats, match="inom"); break
            if difflib.SequenceMatcher(None, a, b).ratio() >= 0.84:
                svaga.append(plats)
        if stark:
            träffar.append(stark)
        elif len(svaga) == 1:
            träffar.append(dict(svaga[0], match="fuzzy"))
            osakra.append({"sökt": namn_cfg, "hittad": svaga[0]["plats"]})
        else:
            saknade.append(namn_cfg)
            if len(svaga) > 1:
                osakra.append({"sökt": namn_cfg, "hittad": [p["plats"] for p in svaga]})
    träffar.sort(key=lambda p: p["plats"].casefold())
else:
    träffar = alla

print(json.dumps({
    "källa": URL,
    "hämtad": datetime.date.today().isoformat(),
    "raknestugor_cfg": raknestugor_cfg,
    "platsfilter": platser_cfg,
    "notiser": notiser,
    "träffar": träffar,
    "saknade": saknade,
    "osakra_matcher": osakra,
    "alla_platser": alla,
}, ensure_ascii=False, indent=1))

if not alla:
    print("VARNING: inga räknestugor parsades — sidans struktur kan ha ändrats", file=sys.stderr)
    sys.exit(1)
