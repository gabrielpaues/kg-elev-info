#!/usr/bin/env python3
"""Parsar Skola24:s schemavisar-text (innerText-slice) till strukturerade dagar.
In: raw-JSON från skrapningen ({"weeks": {"v.37": "..."}}) eller rå textfil.
Ut: JSON per vecka med dagar: datum, start, slut, lektioner (kurs+tid+sal+lärare), händelser, idrott-flagga.

Struktur i texten (empiriskt verifierad på v37–v40 2026-09-06):
  [meta] dag-huvuden (Måndag 7/9 ...) → lektionsblock (3 rader: kod/lärare/sal; 2 rader om sal saknas)
  → specialhändelser (rader "d/m, hh:mm-hh:mm Text" eller "d/m" följt av händelsetext)
  → tidpar (rader "h:mm"), grupperade per dagkolumn i samma ordning.
  Lektionsantal per dag == tidpar per dag. Daggräns i tidflödet = tidsminskning.
Om lektionsantal != tidpar per dag: markera dagen "osäker" — hitta ALDRIG på fördelning.
"""
import json
import re
import sys

KURSMAP = {
    "SVEN": "Svenska", "HIST": "Historia", "KORS": "Körsång", "MATE": "Matematik",
    "SAMH": "Samhällskunskap", "NATU": "Naturkunskap", "ENGE": "Engelska", "IDRO": "Idrott",
    "MODY1000XDEU": "Tyska (nybörjare)", "FILO": "Filosofi", "GEOG": "Geografi", "PSYK": "Psykologi",
    "RELI": "Religionskunskap", "GYAR": "Gymnasiearbete",
}
DAGAR = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag"]
KURSKOD = re.compile(r"^(Mentorstid|Föreläsning|[A-ZÅÄÖ]{3,4}\d[A-Z0-9X]*(?:\s+[a-z]\))?)$")
TIDTOKEN = re.compile(r"^\d{1,2}:\d{2}$")
SPECIAL = re.compile(r"^(\d{1,2}/\d{1,2}),?\s*(\d{1,2}:\d{2}-\d{1,2}:\d{2})?\s*(.+)$")


def kursnamn(kod):
    if kod in KURSMAP:
        return KURSMAP[kod]
    prefix = re.match(r"[A-ZÅÄÖ]{3,4}", kod)
    return KURSMAP.get(prefix.group(0), kod) if prefix else kod


def parse_week(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # 1. Dag-huvuden
    dag_idx = [(i, m.group(1), m.group(2)) for i, l in enumerate(lines)
               if (m := re.match(rf"^({'|'.join(DAGAR)}) (\d{{1,2}}/\d{{1,2}})$", l))]
    if len(dag_idx) < 5:
        return {"fel": f"färre än 5 daghuvuden: {len(dag_idx)}"}
    start = dag_idx[0][0] + 5  # efter Fredag-datumet
    dagar = [{"dag": d[1], "datum": d[2]} for d in dag_idx[:5]]

    # 2. Tidtokens: lektionstider kommer EFTER sista lektionskoden (timgitter-etiketterna
    #    9:00–16:00 före daghuvudena ska inte med). Hitta lektionskoder först.
    pub_idx = next((i for i, l in enumerate(lines) if l.startswith("Senast publicerad")), len(lines))
    kod_idx = [i for i, l in enumerate(lines) if KURSKOD.match(l)]
    if not kod_idx:
        return {"fel": "inga lektionskoder"}
    cutoff = kod_idx[-1]
    tid_rader = [(i, l) for i, l in enumerate(lines[:pub_idx]) if TIDTOKEN.match(l) and i > cutoff]
    if not tid_rader:
        return {"fel": "inga tidtokens efter lektionerna"}
    tid_start = tid_rader[0][0]

    # 3. Specialhändelser = rader mellan lektioner och tidtokens som börjar med d/m
    #    (mittsektionen kan innehålla timgitter-etiketter före lektionerna — de raderas i steg 4:s KURSKOD-koll)
    mitt = lines[start:tid_start]
    ev_split = next((i for i, l in enumerate(mitt) if re.match(r"^\d{1,2}/\d{1,2}", l)), len(mitt))
    lektions_rader = mitt[:ev_split]
    händelse_rader = mitt[ev_split:]
    # rensa bort ev. timgitter-etiketter (h:mm) från lektionsraderna — de är inte lektionskoder
    lektions_rader = [l for l in lektions_rader if not TIDTOKEN.match(l)]

    händelser = {}
    i = 0
    while i < len(händelse_rader):
        m = SPECIAL.match(händelse_rader[i])
        if m and re.match(r"^\d{1,2}/\d{1,2}$", händelse_rader[i].split(",")[0].split(" ")[0]):
            datum = händelse_rader[i].split(",")[0].split(" ")[0]
            rest = händelse_rader[i]
            tider = re.search(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", rest)
            namn = re.sub(r"^\d{1,2}/\d{1,2},?\s*", "", rest)
            if tider:
                namn = re.sub(r"\d{1,2}:\d{2}-\d{1,2}:\d{2}\s*", "", namn)
            händelser.setdefault(datum, []).append({"namn": namn.strip(), "start": tider.group(1) if tider else None, "slut": tider.group(2) if tider else None})
            # nästa rad kan vara händelse utan datum-prefix (t.ex. "Studiedag" efter "10/9")
            i += 1
            while i < len(händelse_rader) and not SPECIAL.match(händelse_rader[i]):
                namn2 = händelse_rader[i].strip()
                if not re.match(r"^\d{1,2}/\d{1,2}$", namn2):  # hoppa över rader som bara är ett datum
                    händelser[datum].append({"namn": namn2, "start": None, "slut": None})
                i += 1
        else:
            i += 1

    # 4. Lektionsblock: 3 rader (kod, lärare, sal) — tolerera 2 (saknas sal)
    lektioner = []
    i = 0
    while i < len(lektions_rader):
        rad = lektions_rader[i]
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
            i += 1  # skräprader hoppas över

    # 5. Tidpar per dagkolumn via tidsminskning (jämför i minuter, ej sträng)
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
    if len(grupper) != 5:
        return {"fel": f"tidgrupper ({len(grupper)}) != 5 dagar", "par": par}

    # 6. Lektioner fördelas på dagar enligt gruppstorlekarna (samma ordning)
    storlekar = [len(g) for g in grupper]
    if sum(storlekar) != len(lektioner):
        return {"fel": f"lektionsantal {len(lektioner)} != tidpar {sum(storlekar)}", "storlekar": storlekar}

    ut = {"dagar": [], "publicerad": lines[pub_idx] if pub_idx < len(lines) else None}
    pos = 0
    for di, (dag, g) in enumerate(zip(dagar, grupper)):
        dag_lek = []
        for p in g:
            lek = lektioner[pos].copy()
            lek["start"], lek["slut"] = p
            dag_lek.append(lek)
            pos += 1
        dag["lektioner"] = dag_lek
        dag["start"] = g[0][0]
        dag["slut"] = g[-1][1]
        dag["idrott"] = any("IDRO" in l["kod"] for l in dag_lek)
        dag["händelser"] = händelser.get(dag["datum"], [])
        ut["dagar"].append(dag)
    return ut


def main():
    src = sys.argv[1]
    if src.endswith(".json"):
        data = json.load(open(src))
        weeks = data.get("weeks", data)
        ut = {}
        for k, v in weeks.items():
            if isinstance(v, str):
                ut[k] = parse_week(v)
        print(json.dumps(ut, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(parse_week(open(src).read()), ensure_ascii=False, indent=2))


main()
