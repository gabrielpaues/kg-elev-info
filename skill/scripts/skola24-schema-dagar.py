#!/usr/bin/env python3
"""Parsar Skola24:s schemavisar-data till strukturerade dagar.

In: raw-JSON från skrapningen.
  Primär källa (robust): "lessonInfo" — dict per vecka med {v.NN: {idx: {timeStart, timeEnd,
  day (1-5), block, texts: [kod, lärare, sal, ...]}}} — dumpad ur Vue-VM
  (NovaSoftware.Widgets.Base.applications[<guid>].timetable.lessonInfo).
  Flat-texten ("weeks": {"v.NN": "..."}) används enbart för specialhändelser
  (Studiedag/Gula dagar, "d/m, hh:mm-hh:mm Text") och publiceringstid.

Ut: JSON per vecka med dagar: datum, start, slut, lektioner (kurs+tid+sal+lärare),
händelser, idrott-flagga. Alla fem vardagar finns alltid med — även dagar utan
celler (Studiedag/Gul dag).

Fallback (om lessonInfo saknas): legacy flat-text-parse. Där hanteras
(a) "Lunch"-rader som ett_tid_par_utan lektionsblock och
(b) dagar utan tidpar (Studiedag) — tidsminskningsgrupperingen kan då inte skilja
dagar, så flat-fallbacken antar lika cellfördelning endast när antal tidpar > 0
per dag; annars "osäker". Hitta ALDRIG på fördelning.

Empiriskt: lessonInfo-motorn kalibrerad på v45-v50 2026-11-01 (v45 med tom
onsdag/Studiedag, v46-v50 med Lunch-celler).
"""
import json
import re
import sys
from datetime import datetime, timedelta

KURSMAP = {
    "SVEN": "Svenska", "HIST": "Historia", "KORS": "Körsång", "MATE": "Matematik",
    "SAMH": "Samhällskunskap", "NATU": "Naturkunskap", "ENGE": "Engelska", "IDRO": "Idrott",
    "MODY1000XDEU": "Tyska (nybörjare)", "FILO": "Filosofi", "GEOG": "Geografi", "PSYK": "Psykologi",
    "RELI": "Religionskunskap", "GYAR": "Gymnasiearbete",
}
DAGAR = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag"]
KURSKOD = re.compile(r"^(Mentorstid|Föreläsning|Lunch|[A-ZÅÄÖ]{3,4}\d[A-Z0-9X]*(?:\s+[a-z]\))?)$")
TIDTOKEN = re.compile(r"^\d{1,2}:\d{2}$")
SPECIAL = re.compile(r"^(\d{1,2}/\d{1,2}),?\s*(\d{1,2}:\d{2}-\d{1,2}:\d{2})?\s*(.+)$")


def kursnamn(kod):
    if kod in KURSMAP:
        return KURSMAP.get(kod, kod)
    prefix = re.match(r"[A-ZÅÄÖ]{3,4}", kod)
    return KURSMAP.get(prefix.group(0), kod) if prefix else kod


def vecka_dagar(vk):
    """Måndagens ISO-datum för veckonummer, schemavisarårets kontext 2026 (avleds ur flat-text rader)."""
    return None  # datum skrapas ur flat-textens daghuvuden istället


def parse_events(text):
    """Specialhändelser ur flat-texten: rader som börjar med d/m följda av lokala rader."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    pub_idx = next((i for i, l in enumerate(lines) if l.startswith("Senast publicerad")), len(lines))
    # händelsesektionen ligger mellan sista schemacellen och tidtokens/publicerad
    # robust höjd: hitta "Studiedag"-typiska rader direkt — rader efter sista lektionsblocket
    tid_idx = [i for i, l in enumerate(lines) if TIDTOKEN.match(l)]
    ev_rader = []
    if tid_idx:
        # tidtokens kommer i block efter händelser; händelser between last lektionsblock and first tid-block
        last_kod = max((i for i, l in enumerate(lines[:pub_idx]) if KURSKOD.match(l)), default=None)
        if last_kod is not None:
            ev_rader = lines[last_kod + 1:tid_idx[-1]]
    händelser = {}
    i = 0
    while i < len(ev_rader):
        m = SPECIAL.match(ev_rader[i])
        if m and re.match(r"^\d{1,2}/\d{1,2},?$", ev_rader[i].split(",")[0].split(" ")[0] + ("," if ev_rader[i].split(",")[0].endswith(",") else "")):
            datum = ev_rader[i].split(",")[0].split(" ")[0].rstrip(",")
            rest = ev_rader[i]
            tider = re.search(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", rest)
            namn = re.sub(r"^\d{1,2}/\d{1,2},?\s*", "", rest)
            if tider:
                namn = re.sub(r"\d{1,2}:\d{2}-\d{1,2}:\d{2}\s*", "", namn)
            bara_datum = not namn.strip()
            if bara_datum and i + 1 < len(ev_rader):
                namn = ev_rader[i + 1].strip()
                i += 2  # (datum-)+tidsrad + namn-rad konsumerade
                händelser.setdefault(datum, []).append({"namn": namn, "start": tider.group(1) if tider else None, "slut": tider.group(2) if tider else None})
                continue
            händelser.setdefault(datum, []).append({
                "namn": namn.strip() or (ev_rader[i + 1].strip() if i + 1 < len(ev_rader) else ""),
                "start": tider.group(1) if tider else None,
                "slut": tider.group(2) if tider else None,
            })
            i += 1
            while i < len(ev_rader) and not SPECIAL.match(ev_rader[i]):
                namn2 = ev_rader[i].strip()
                if not re.match(r"^\d{1,2}/\d{1,2}$", namn2):
                    händelser[datum].append({"namn": namn2, "start": None, "slut": None})
                i += 1
        else:
            i += 1
    return händelser


def hhmm(t):
    """'11:20:00' -> '11:20'"""
    return (t or "")[:5]


def parse_week_lessons(lessons, text):
    """lessonInfo-motor: bygger alla 5 dagar direkt ur VM-data."""
    if not isinstance(lessons, dict) or not lessons:
        return {"fel": "lessonInfo tom/saknad"}
    if not text:
        return {"fel": "flat-text saknad (behövs för daghuvud-datum)"}

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    dag_idx = [(m.group(1), m.group(2)) for l in lines
               if (m := re.match(rf"^({'|'.join(DAGAR)}) (\d{{1,2}}/\d{{1,2}})$", l))]
    if len(dag_idx) < 5:
        return {"fel": f"färre än 5 daghuvuden i flat-text: {len(dag_idx)}"}

    händelser = parse_events(text)

    # gruppera lektioner per dag (1=måndag)
    celler = {}
    for L in lessons.values():
        if L is None:
            continue
        dag = int(L.get("day") or 0)
        if dag < 1 or dag > 5:
            continue
        texts = [t for t in (L.get("texts") or []) if t]
        kod = texts[0] if texts else (L.get("blockName") or "Okänd")
        lärare = texts[1] if len(texts) > 1 else ""
        sal = texts[2] if len(texts) > 2 else ""
        celler.setdefault(dag, []).append({
            "kod": kod, "kurs": kursnamn(kod), "lärare": lärare, "sal": sal or None,
            "start": hhmm(L.get("timeStart")), "slut": hhmm(L.get("timeEnd")),
        })

    publicerad = next((l for l in lines if l.startswith("Senast publicerad")), None)
    ut = {"dagar": [], "motor": "lessonInfo"}
    for i, (dag, datum) in enumerate(dag_idx[:5], start=1):
        d_lek = sorted(celler.get(i, []), key=lambda c: c["start"])
        ut["dagar"].append({
            "dag": dag, "datum": datum,
            "start": d_lek[0]["start"] if d_lek else None,
            "slut": d_lek[-1]["slut"] if d_lek else None,
            "lektioner": d_lek,
            "idrott": any("IDRO" in c["kod"] for c in d_lek),
            "händelser": händelser.get(datum, []),
        })
    return ut


def parse_week_legacy(text):
    """Legacy flat-text-parser med Lunch- och tom-dag-tolerans."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    dag_idx = [(i, m.group(1), m.group(2)) for i, l in enumerate(lines)
               if (m := re.match(rf"^({'|'.join(DAGAR)}) (\d{{1,2}}/\d{{1,2}})$", l))]
    if len(dag_idx) < 5:
        return {"fel": f"färre än 5 daghuvuden: {len(dag_idx)}"}

    händelser = parse_events(text)
    kod_idx = [i for i, l in enumerate(lines) if KURSKOD.match(l)]
    if not kod_idx:
        return {"fel": "inga lektionskoder"}
    pub_idx = next((i for i, l in enumerate(lines) if l.startswith("Senast publicerad")), len(lines))
    cutoff = kod_idx[-1]
    tid_rader = [(i, l) for i, l in enumerate(lines[:pub_idx]) if TIDTOKEN.match(l) and i > cutoff]
    if not tid_rader:
        return {"fel": "inga tidtokens efter lektionerna"}
    tid_start = tid_rader[0][0]

    mitt = lines[dag_idx[0][0]:tid_start]
    ev_split = next((i for i, l in enumerate(mitt) if re.match(r"^\d{1,2}/\d{1,2}", l)), len(mitt))
    lektions_rader = [l for l in mitt[:ev_split] if not TIDTOKEN.match(l)]

    # lektionsblock: Lunch är en-radigt; övriga 3 rader (kod/lärare/sal) — tolerera 2
    lektioner = []
    i = 0
    while i < len(lektions_rader):
        rad = lektions_rader[i]
        if rad == "Lunch":
            lektioner.append({"kod": "Lunch", "kurs": "Lunch", "lärare": "", "sal": None})
            i += 1
            continue
        if KURSKOD.match(rad):
            lärare = lektions_rader[i + 1] if i + 1 < len(lektions_rader) else ""
            sal = lektions_rader[i + 2] if i + 2 < len(lektions_rader) else None
            steg = 3
            if i + 2 < len(lektions_rader) and (KURSKOD.match(lektions_rader[i + 2]) or re.match(r"^\d{1,2}:\d{2}", lektions_rader[i + 2])):
                sal = None
                steg = 2
            lektioner.append({"kod": rad, "kurs": kursnamn(rad), "lärare": lärare, "sal": sal})
            i += steg
        else:
            i += 1

    def minuter(t):
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    tider = [l for _, l in tid_rader]
    par = [(tider[j], tider[j + 1]) for j in range(0, len(tider) - 1, 2)]
    grupper = [[]]
    for p in par:
        if grupper[-1] and minuter(p[0]) < minuter(grupper[-1][-1][1]):
            grupper.append([])
        grupper[-1].append(p)
    om_grupper = len(grupper)
    if om_grupper == 5 and sum(len(g) for g in grupper) == len(lektioner):
        ut = {"dagar": [], "motor": "flat-text"}
        pos = 0
        for dag, g in zip(dag_idx[:5], grupper):
            dag_lek = []
            for p in g:
                lek = lektioner[pos].copy()
                lek["start"], lek["slut"] = p
                dag_lek.append(lek)
                pos += 1
            ut["dagar"].append({
                "dag": dag[1], "datum": dag[2],
                "start": g[0][0] if g else None, "slut": g[-1][1] if g else None,
                "lektioner": dag_lek,
                "idrott": any("IDRO" in l["kod"] for l in dag_lek),
                "händelser": händelser.get(dag[2], []),
            })
        return ut
    # osäker flat-distribution — trappa upp (hitta ALDRIG på fördelning)
    return {"fel": f"osäker flat-fördelning (grupper {om_grupper}, lektioner {len(lektioner)}, tidpar {len(par)})"}


def main():
    src = sys.argv[1]
    if src.endswith(".json"):
        data = json.load(open(src))
        weeks = data.get("weeks", data)
        lessons_all = data.get("lessonInfo") or {}
        ut = {}
        for k, v in weeks.items():
            if isinstance(v, str):
                if k in lessons_all and lessons_all[k]:
                    ut[k] = parse_week_lessons(lessons_all[k], v)
                    if "fel" in ut[k]:
                        ut[k]["flat_fallback"] = parse_week_legacy(v)
                else:
                    ut[k] = parse_week_legacy(v)
        print(json.dumps(ut, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(parse_week_legacy(open(src).read()), ensure_ascii=False, indent=2))


main()
