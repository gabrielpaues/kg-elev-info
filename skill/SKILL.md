---
name: kg-elev-info
description: |
  Veckorapport för ett barns skola (Kungsholmens gymnasium / Stockholms musikgymnasium).
  Hämtar info från skolans tre system — Infomentor (nyheter/samtal), Skola24 (schema/frånvaro)
  och Edlevo (betyg) — via debug-Chrome där användaren loggat in med BankID. Bygger rapport
  med: viktiga händelser kommande vecka, åtgärder inför veckan, dagar med särskilt att ha
  med (bl.a. idrottsdagar), schema per dag, konserter eleven medverkar i, samt framåtblick på
  kommande veckor/termin. Personspecifik konfiguration (namn, klass, kammarkör, mottagare)
  läses från data/elev.local (gitignored) och frågas efter vid första körningen. Trigga på:
  veckorapport skola, skolan den här veckan, vad händer i skolan, barnets skola,
  Kungsholmens gymnasium, skola-veckorapport, kg-elev-info.
---

# Skola Veckorapport

Sammanställ veckans och terminens läge från skolans tre system. Rapport beror på **manuell BankID-inloggning av användaren** — aldrig automatisera inloggning.

**Mappstruktur:** `~/github/kg-elev-info/` — `rapporter/` (veckorapporter), `raw/` (skrapad JSON), `data/` (terminsdatum), `chrome-profile/` (debug-Chromes profil). Aldrig in i git (personuppgifter) — se .gitignore; personspecifik konfiguration ligger enbart i `data/elev.local`.

---

## 1. Konfiguration (första körningen, eller om elev.local saknas)

Kolla först: `cat ~/github/kg-elev-info/data/elev.local`. Saknas filen — fråga användaren (question-tool), skriv filen, fortsätt sedan:

1. **ELEV_NAMN** — elevens förnamn (används i rapportrubriker, kalenderhändelser och iMessage-texter)
2. **KLASS** — klasskod (om okänd: lämna tom; detekteras vid första skrapningen enligt §6)
3. **ARSKURS** — 1–3 (för konsertfiltrering "hela årskurs N")
4. **KAMMARKOR** — `true`/`false` (styr om kammarkörens konserter tas med)
5. **KALENDER_NAMN** — iCloud-kalenderns namn (default: `Skola - <ELEV_NAMN>`)
6. **MOTTAGARE** — kommaseparerade iMessage-mottagare (telefonnummer/Apple-ID, utan mellanrum)
7. **RAKNESTUGOR** — `true`/`false` (styr om Mattecentrums räknestugor tas med i rapporten; saknas värdet → fråga användaren)
8. **RAKNESTUGOR_PLATSER** — kommaseparerade platsnamn, EXAKT stavade som på mattecentrum.se; vid `RAKNESTUGOR=true` + saknas värdet: kör `python3 ~/github/kg-elev-info/skill/scripts/raknestugor.py --list`, visa platslistan och låt användaren välja (multiple: true), skriv sedan in namnen ordagrant

Format:

```
ELEV_NAMN=<förnamn>
KLASS=<XxNNxx>
ARSKURS=<1-3>
KAMMARKOR=<true|false>
RAKNESTUGOR=<true|false>
RAKNESTUGOR_PLATSER=<plats1>,<plats2>
KALENDER_NAMN=Skola - <förnamn>
MOTTAGARE=<nr1>,<nr2>
```

Filen är gitignored — ändra den direkt vid behov, committa aldrig.

## 2. Starta debug-Chrome

```zsh
~/github/kg-elev-info/skill/scripts/start-chrome.sh
```

Port 9222. Isolerad profil → inloggningar finns kvar mellan körningar (kan kräva nytt BankID när sessioner löper ut). Om 9222 är taget: `CDP_PORT=<n>` till `cdp.mjs`.

## 3. Öppna tabbar

**Befintliga tabbar återanvänds — öppna aldrig dubbletter.** Kör `node $C list` först. Alla tre systemen delar samma Siteminder-SSO: har någon session levt kvar kan en sluten tab återställas med omnavigering till service-URL:en (SMSESSION-kakan gäller fortfarande) utan nytt BankID. `new` startar en NY SAML-transaction — blir assertionen stale först av den → `HTTP 400 Bad Request` (se kalibreringslektionen i §4). Öppna bara `new` för system utan tab, och låt vid inloggning bara ETT SAML-flöde åt gången köras.

```zsh
C=~/github/kg-elev-info/skill/scripts/cdp.mjs
node $C list
# Tab saknas → öppna:
node $C new "https://sso.infomentor.se/login.ashx?idp=stockholm_par"
node $C new "https://stockholm.skola24.se"
node $C new "https://education.service.tieto.com/WE.Education.Spaces/Start?Actor=Actor_Relative&idpMethod=SAML&domain=StockholmEdu"
# Tab finns men gammal/fel → OMnavigera (återanvänder sessionen):
node $C navigate <idx> "https://stockholm.skola24.se"
node $C list
```

Redan inloggad (sessionerna lever) → hoppa till steg 4.

## 4. Vänta på BankID-inloggning

Säg till användaren: *logga in i de tre Chrome-fönstren (Infomentor, Skola24, Edlevo) — säg till när klart.* Vänta på bekräftelse, verifiera därefter:

```zsh
node $C eval <infomentor-idx> ~/github/kg-elev-info/skill/scripts/recon.mjs
```

`loggedInGuess: false` eller loginformulär i text → fråga igen. Fortsätt aldrig på osäker inloggning.

**⚠️ Kalibreringslektion 2026-09-06:**
- Kör bara **en SAML-inloggning i taget**. Tre parallella flöden i samma Siteminder-session → assertionen expirerar → `HTTP 400 Bad Request` på `saml2sso?SMASSERTIONREF=QUERY`. Åtgärd: navigera om tabben till service-URL:en — ofta lever SMSESSION-kakan kvar och inloggningen sker utan nytt BankID.
- Skola24 kan svara 500 vid blinda API-anrop utan rätt parametrar — kör bara sidans egna UI-flöden.

## 5. Skrapa alla tre (kalibrerade recept 2026-09-06)

Spara rå JSON per system i `~/github/kg-elev-info/raw/YYYY-MM-DD-<system>.json`. Råtext är sanningens källa — inget i rapporten får komma från annat än dessa data + terminsdatum.

cdp-kommandon: `list | new <url> | navigate <idx> <url> | eval <idx> <fil.js> | click <idx> <css-sel> | net <idx> <sek> | close <idx>`. `eval`-filer får vara fristående (top-nivå `return` omsluts av `(async()=>{...})()`); `await` och `setTimeout` är OK. **JS-klick fungerar inte i Infomentor/KO — läs data ur KO-VM:en eller använd `click` (trusted CDP-input); `element.closest('a.tile').click()` via JS fungerar bara för tile-navigering.**
**Håll varje eval kort (≈10 s arbete max)** — en eval med sekventiella klickar + väntar tappar sitt resultat mot shell-timeout. Splitta: click → sleep i skalet → ny eval. Läsning av VM-data (se 5a-nyheter) klickar inte alls och är därför förstahandsval.

### 5a. Infomentor (hub.infomentor.se, Knockout-SPA)

Direkta hash-ruter (navigera med `$C navigate <idx> "https://hub.infomentor.se/#/communication/news"`):

| Ruta | Innehåll |
|------|----------|
| `#/communication/news` | NYHETER — titel + av + datum; brödtext via KO-VM (recept nedan) |
| `#/communication/links` | LÄNKAR-tabellen (namn/beskrivning/url) |
| `#/communication/files` | nya filer (namn/datum/storlek) — tom ruta = inga nya filer |
| `#/communication/consent` | SAMTYCKEN — kontrollera "Inga aktiva samtycken" |
| `#/` | tiles + NOTISER-panel (punktlista med datum, t.ex. "Nyhet publicerad 26-08-26") |

**Nyhetsbrödtext via Knockout-VM (kalibrerat 2026-09-15):** varken JS-klick eller trusted CDP-klick öppnar nyhetsdialogen. Läs i stället data direkt ur VM:en — listobjekten är `div[class*="__news-item__"]` med inre `button.item-card`:

```js
const items = [...document.querySelectorAll('div[class*="__news-item__"] button.item-card')]
const seen = new Set(), news = []
for (const el of items) {
  const d = ko.toJS(ko.contextFor(el).$data)
  if (seen.has(d.id)) continue; seen.add(d.id)
  news.push({ titel: d.title, av: d.publishedBy, datum: d.publishedDateString,
    innehall: (d.content || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim() })
}
```

`content` är HTML → stripa taggar. Namngivna bilder/bilagor finns i `attachments`.

Kalender: sub-app med egen router. Navigera `#/`, JS: `document.querySelector('#calendarv2').closest('a.tile').click()`, vänta 4 s, landar på `#/communication/whole_week` (2026-09-15; tidigare `#/calendarv2/whole_week` — kontrollera hashen om strukturen ändrats). Loopa veckor: `aria-label="Nästa vecka"`-knapp, 2,5 s per vecka, en eval per vecka. Klipp text: `t.match(/Vecka \d\d[\s\S]*/)` och klipp bort spårbrus på `\nInformation\nNYHETER` (NOTISER-panelen finns inte alltid i texten). Innehåll: skoldagstyper (Gul heldag/eftermiddag/förmiddag med tider = avvikande skoldag!), prov/inlämningar (Examinationsschema), temadagar, elevhälsa, körhändelser.

Guld i kalendern: raden "Gul heldag"/"Gul eftermiddag" betyder förkortad/avvikande skoldag → både schema-avvikelse och praktisk planering.

Mötesbokning (`#/meeting`): kolla om öppna bokningsfönster finns — sidan visar "Du har inga bokade möten" eller bokade möten (bekräftat 2026-09-15). Aktiva bokningsperioder → rapportera under Åtgärda.

### 5b. Skola24 (websthlm.skola24.se)

| URL | Innehåll |
|-----|----------|
| `/portal/start` | portalmeny (Schemavisare, Elev/Klass-bild, Anmäla frånvaro, Ansöka om ledighet) |
| `/portal/start/absence/leave-application` | ledighetsansökningar — "Visa ledighetsansökningar" är accordion, expanderas inte via JS-klick; låt användaren kolla manuellt eller använd `$C click 0 "h2"` — OBS: kräver trusted click |
| Schemavisare → veckor | se recept nedan |

Schema-recept:
1. Navigera tabben till Schemavisare (JS-klick på länken funkar) → `/portal/start/timetable/timetable-viewer/stockholm.skola24.se/`.
2. Skrapa aktuell vecka direkt (dropdownen öppnas på den), sedan byt vecka: öppna veckodropdown med JS-klick på `button.w-arrow` med `aria-label="Tryck för att öppna meny"`, 0,9 s.
3. Klicka vecka: `[...document.querySelectorAll('a')].find(a => a.innerText.trim().startsWith('v.39 '))` (obs: med avslutande mellanslag), 3 s.
4. Klipp: från `'Visa schema för'` till `'Senast publicerad'` i `document.body.innerText`. Sista raden = senaste publiceringstid (rapportera den!).

**Spara ALLA veckor i EN fil** med exakt denna form — `skola24-schema-dagar.py` kräver den (2026-09-15: en fil per vecka gav `färre än 5 daghuvuden: 0`):

```json
{ "system": "skola24", "typ": "schemavisare", "hamtat": "ÅÅÅÅ-MM-DD",
  "publicerad": "ÅÅÅÅ-MM-DD tt:tt (Kungsholmens gymnasium)",
  "weeks": { "v.38": "text...", "v.39": "text...", "v.40": "text..." } }
```

Parserns utdata: dict nycklad per vecka (`"v.39": { "dagar": [...] }`) — `dagar` har ett element per vardag.

Schema-texten innehåller: dagar (Måndag 7/9 …), lektioner (kurskod, lärarinitialer, rumsnr) och specialraderna under veckan: "10/9, 9:00-12:00 Friluftsdag", "Studiedag", "9/9, 12:30-17:00 Studieeftermiddag" — dessa är guld, korsreferera med Infomentor-kalendern.

**Strukturerad parsing per dag (krav för start/sluttider + idrottsdagar):**

```zsh
python3 ~/github/kg-elev-info/skill/scripts/skola24-schema-dagar.py ~/github/kg-elev-info/raw/<datum>-skola24-schema.json > ~/github/kg-elev-info/raw/<datum>-skola24-dagar.json
```

- Ger per dag: datum, start (första lektion), slut (sista lektion), lektioner med kurs/tid/sal/lärare, händelser, `idrott`-flagga (IDRO-kod).
- Validering inbyggd: dagarna splittas via tidsminskning i tidflödet + krav att lektionsantal == tidpar per dag. Returnerar `fel` → rapportera dagen som "fördelning osäker" — hitta ALDRIG på fördelning.
- Empiriskt stabil på v37–v40 2026-09-15 (repriserad 2026-09-06 och 2026-09-15). Om Skola24 ändrar rendering: kör recon + kalibrera (se §10). Live-DOM-extraktion per dagkolumn är den robusta uppgraderingen om flat-parsningen slutar fungera.

### 5c. Edlevo (education.service.tieto.com)

Startsidan listar `div.menu-card` (Barnomsorgsansökan, Familjeförhållanden, Registrera inkomst, Studieplan …). Studieplan: JS-klick på card med texten "Studieplan" → ny sida `USStudyPlanGuardian?childId=...` med tabeller: Planerade / Pågående / Avslutade + Studieplansanteckningar. Dumpa hela (kurser med poäng, perioder, betyg). Betyg spelar roll först vid avslutade kurser; pågående = läsårets plan. Kolla inför utvecklingssamtal.

## 6. Hämta publika terminsdatum + konserter + räknestugor

```zsh
python3 ~/github/kg-elev-info/skill/scripts/hamta-lasaret.py ~/github/kg-elev-info/data/lasaret-datum.md
```

Skriptet hämtar ALLA terminssektioner strukturellt ((Höst|Vår)terminen ÅÅÅÅ) — robust när skolan byter läsår eller plockar bort höstterminen. Tidigare sed-kommando på rå HTML brast på båda punkterna (tag-soppa + försvunnen höstterminssektion → tomt resultat). Kör ALLTID scriptet, aldrig sed på HTML.

**Konserter** (Kungsholmens är också Stockholms musikgymnasium — eleven deltar i körkonserter):

```zsh
python3 ~/github/kg-elev-info/skill/scripts/konserter.py --klass <KLASS>
```

- `KLASS` läses från `data/elev.local`. Om den är tom: hitta klasskoden i Infomentor-kalendern (t.ex. "XxNNxx LÄRARE inlämning" / "Sv1 XXNNXX Prov") — mönstret `\b[NS][a-z]\d{2}[a-z]{2}\b`, välj den som återkommer i elevens poster. Årskurs härleds ur koden (NN = antagningsår); verifiera mot Edlevo-kurslistan (enstaka Nivå 1-kurser = åk 1) och skriv in i elev.local.
- Filtreringen matchar: (a) klasskoden utskriven bland medverkande, (b) "hela årskurs N", (c) hela skolan — MEN BARA om ingen specifik grupp (annan klass/årskurs) nämns (tidigare bugg: "Årskurs 3 från skolan" matchade felaktigt "hela skolan").
- Kammarkören är separat antagen — anta ALDRIG att eleven sjunger där. `KAMMARKOR=true/false` i elev.local styr: false → exkludera kammarkörens konserter utan vidare kontroll; true → inkludera dem. Saknas värdet → fråga användaren en gång och skriv in det.
- **Körklasser ≠ kammarkören (kalibrerat 2026-09-15).** Evenemang märkta "ALLA körklasser" (rep, konserter, tutti) i Infomentor-kalendern gäller eleven om KORS1000X/Körsång finns i Skola24-schemat eller Edlevo-studieplanen — oavsett `KAMMARKOR=false` (flaggan styr endast kammarkören). Kontrollera alltid Körsång-kursen innan du exkluderar körhändelser; utan stöd i schema/studieplan → lista under Framåt med källcitat.
- Personalinriktade kalenderposter (t.ex. "Sektionskonferens", kategori Allmänt): kolla Skola24 — oförändrat eleverschema där → inte en elevhändelse; ta endast med under Framåt med källcitat.
- Konsertbiljetter med datum för biljettsläpp → går under "Åtgärda i förväg" om släppet ligger inom rapportperioden, annars under "Framåt".

**Räknestugor** (Mattecentrum, filtreras på valda platser ur elev.local):

```zsh
python3 ~/github/kg-elev-info/skill/scripts/raknestugor.py > ~/github/kg-elev-info/raw/$(date +%F)-raknestugor.json
```

- Kör ENDAST om `RAKNESTUGOR=true` i elev.local (skriptet läser config själv; vy över alla platser: `raknestugor.py --list`). Saknas nycklarna §1:s regler gäller.
- JSON-utdata: `träffar` (plats/adress/url/tider + match-typ), `notiser` (t.ex. "Räknestugorna stängda v.44." — kopiera till rapportens räknestugor-sektion), `saknade` (config-namn som inte hittades → föreslå stavkorrigering), `osakra_matcher` (nära stavning — förfråga användaren, skriv aldrig in osäker träff tyst).
- Platser matchas exakt eller in-under-sträng (skiftlägesokänsligt) — vid fuzzy-träff: uppdatera elev.local till den exakta stavningen från sidan.
- Räknestugorna är ÅTERKOMMNA veckoaktiviteter utan särskilda datum → hamnar bara i rapportens räknestugor-sektion, ALDRIG i kalendersyncen (§8; endast daterade saker).
- Parsern körs på serverrenderad HTML (`nav.tutoring-locations` + h2/span/h3-par). Tom platslista → sidans struktur ändrad: kalibrera enligt §10.

## 7. Bygg rapport

Spara som `~/github/kg-elev-info/rapporter/YYYY-MM-DD-vecka-<WW>.md` (veckonummer = kommande vecka, programmatiskt: `date -v+1w +%V`).

```markdown
# Veckorapport — Kungsholmens gymnasium
Vecka [WW], [mån dd]–[sön dd]. Sammanställd [YYYY-MM-DD].

## I veckan som går (kvarvarande v[WW-1])
[Bara när rapporten körs på måndag–fredag i den pågående veckan: kvarvarande dagars prov/inlämningar/avvikande skoldagar — korthugget, med källa. Kör rapporten på helgen/söndag → sektionen utelämnas helt.]

## Viktigt den kommande veckan
- [dag dd/mm] [händelse] — [källa: Infomentor/Skola24/terminsdatum]

## Åtgärda i förväg
- [åtgärd] — [deadline] — [källa]
[inget: "Inget just nu"]

## Schema per dag
| Dag | Start | Slut | Lektioner | Notera |
[från skola24-dagar.json: alla fem vardagar, även normala — start = första lektion, slut = sista. Idrott-dagar i fetstil + "gymnastikkläder" i Notera. Återkommande mönster (t.ex. "Idrott varje onsdag 11:25") skrivs som rad under tabellen om det är synligt i ≥2 veckors data.]

## Särskilt att ha med
- [dag dd/mm] [vad] — [anledning]
[IDRO-dagar → ALLTID gymnastikkläder här, även veckor utan andra avvikelser — syftet är att hen ska komma ihåg att tvätta/packa]
[inget: "Inga dagar med särskilda saker denna vecka"]

## Schema vid avvikelse
[från Skola24: lediga dagar, avvikande tider, frånvaro som redan är anmäld]

## Räknestugor (Mattecentrum)
[ENDAST om RAKNESTUGOR=true — annars uteslut sektionen helt.]
- [dagar kl tt] — [plats], [adress] — [url]
[notiser från raw (`stängda v.NN`) som egen rad högst upp i sektionen]
[inga träffar: "Inga räknestugor matchar valda platser — kontrollera RAKNESTUGOR_PLATSER i data/elev.local"]

## Konserter ([ELEV_NAMN] medverkar)
- [dag dd/mm kl tt] — [titel], [plats] — [match: klass/årskurs/hela skolan] — [biljettinfo om aktuell]
[inga kommande: "Inga konserter med elevens deltagande de närmaste veckorna"]

## Framåt — kommande veckor
| Datum | Vad | Källa |
|-------|-----|-------|
| [dd/mm] | [händelse] | [Infomentor/Skola24/terminsdatum] |

[Kommande 4–8 veckor + terminsdatum så långt räckvidden finnes.]
```

**Regler:**
- Rapporten vänder sig till vårdnadshavaren — formulera åtgärder som "boka utvecklingssamtal", inte "kontakta mentorn" utan anledning.
- Veckonumret räknar framåt även mitt i veckan (`date -v+1w +%V` på en tisdag ger nästa helvecka) — därför sektionen "I veckan som går" ovan; dess daterade poster ska också med i kalendersyncen (§8).
- Veckodag ALLTID programmatiskt från datum (`date -j -f "%Y-%m-%d" ... +%A` eller python). Aldrig härledas från minne.
- Osäker tolkning av raw-text → lista under "Framåt" med källcitat, aldrig som säker händelse med falsk precision.
- Frånvaro/betyg som verkar gamla → inte i veckans sektioner; kontrollera datum i texten.
- Tomma sektioner får aldrig hoppas över.
- Skrivregler enligt AGENTS.md (ingen inflation, inga påhittade datum, neutral ton).
- Avsluta svaret till användaren med rapportens sökväg + de 3 viktigaste raderna, inte hela rapporten i chatten.

## 8. Kalendersync (iCloud, delad med eleven)

**Kalendern (namn från `KALENDER_NAMN` i elev.local) MÅSTE ligga under iCloud-kontot.** AppleScript exponerar inte konton och `make new calendar` landar i default-kontot (oftast On My Mac) — skapa därför kalendern engångsvis manuellt: Cal.app → högerklicka **iCloud-rubriken** i sidofältet → Ny kalender → namnet från KALENDER_NAMN. Skriptet fyller däremot events via AppleScript obehindrat (osascript har egen behörighet; EventKit-via-Swift nekades TCC i denna miljö, försök ej igen).

Efter rapporten: bygg `~/github/kg-elev-info/data/kalender-events.json` av rapportens daterade poster (I veckan som går, Viktigt kommande vecka, Schema-avvikelser, Framåt — prov, inlämningar, avvikande dagar, lov). Syntax:

```json
{ "events": [
  { "date": "2026-09-10", "time": "09:00", "endTime": "12:00", "title": "Friluftsdag åk 1", "desc": "Källa + vad som gäller" },
  { "date": "2026-10-26", "endDate": "2026-10-30", "endTime": "23:59", "allday": true, "title": "Höstlov" }
] }
```

**Flöde med AI-dubletturval (kalibrerat 2026-09-15 — skriptets dup-koll är EXAKT på summary + start date och skapar kopia när titeln ändrats):**

1. **Dumpa kalendern först** (läser, skapar inget):
   ```zsh
   node ~/github/kg-elev-info/skill/scripts/calendar-sync.mjs dump ~/github/kg-elev-info/data/kal-dump.json
   ```
   → `{ events: [{uid, title, start, end, desc}] }` för alla framtida events. iCloud-frågan är långsam — räkna med 1–3 min, timeout 300 s.
2. **AI-jämför ny-proposals mot dumpen semantiskt.** Kärnproblemet: händelser "byter namn när mer info kommer" (exempel: "Rep i Konserthuset 15:30–20:00 (exakta tider kommer senare)" → exakta tider; "X — eleven medverkar"-suffix vs kort titel; språkdag-benämning vs gul dag; publktid vs elevtid samma dag). Det går INTE att skripta robust och importeras ALDRIG med fuzzy-matchning — två olika prov samma dag får inte slås ihop. AI:n avgör per par: (a) samma underliggande sak trots annan formulering/tid → match; (b) samma dag men olika saker → INTE match; (c) befintlig post ingen längre motsvarar (withdrawn/inställd) → kandidat för tillbakadragning.
3. **Uppdatera samnyttjade poster i stället för att skapa nya** — skriv `data/kalender-updates.json` och kör:
   ```zsh
   node ~/github/kg-elev-info/skill/scripts/calendar-sync.mjs apply-updates ~/github/kg-elev-info/data/kalender-updates.json
   ```
   ```json
   { "updates": [ { "uid": "…", "title": "Höstkonsert i Konserthuset", "date": "2026-10-20", "time": "15:00", "endTime": "22:00", "desc": "Elevtider … publik 19.30. Källa: Infomentor + skolans konsertsida" } ] }
   ```
   Endast angivna fält ändras; tider ändras bara när `date` medföljer.
4. **Dubbletter/tillbakadragna poster tas BORT bara efter uttryckligt användargodkännande** — visa konkreta titlar+datum i chatten (som commit-regeln), vänta på ja, spara `{ "uids": [...] }` och kör:
   ```zsh
   node ~/github/kg-elev-info/skill/scripts/calendar-sync.mjs remove ~/github/kg-elev-info/data/kalender-remove.json
   ```
5. **Create-pass som backstop** (skapar nu bara verkligt nya):
   ```zsh
   node ~/github/kg-elev-info/skill/scripts/calendar-sync.mjs ~/github/kg-elev-info/data/kalender-events.json
   ```
6. Rapportera kort i chatten: X uppdaterade (vad som ändrats), Y raderade (godkänt), Z skapade, H hoppade över.

**Review-regler för AI-steget:** matcha på dag ±1 dygn + samma sak trots olika formulering; vid match vinner senaste körningens titel och den bästa infon (exakta tider, källor) samlas i desc; behöver bara uppdatera den ena av två dubbletter — den andra hamnar i steg 4. Osäker → låt bli och fråga användaren.

- Kalendern heter enligt `KALENDER_NAMN` i elev.local (scriptet skapar den om den saknas i create-pass — kontrollera då att den hamnar i iCloud, inte On My Mac).
- Heldagar utan känd tid: `allday: true`; flerdagarshändelser (lov): `endDate`.
- Endast daterade saker → kalendern. Vaga uppgifter ("kolla mentorns info") hamnar bara i rapporten.
- Delning med elevens/familjens Apple ID: görs endast manuellt i Cal.app (delningsknapp) — kan ej skriptas.

## 9. Dela rapporten (Dropbox-länk + iMessage)

Efter rapporten + kalendersync (§8):

```zsh
~/github/kg-elev-info/skill/scripts/share-report.sh ~/github/kg-elev-info/rapporter/<rapport>.md
```

Flödet: MD → stilad HTML (`md2html.py`) → PDF (debug-Chrome, `cdp.mjs pdf`) → Dropbox `Skola-Rapporter/rapport-senaste.pdf` (mode=overwrite → **länken är beständig mellan veckor**) → delbar länk → skrivs till `data/last-delad-lank.txt` + stdout (direktlänk `dl.dropboxusercontent.com` också). Arkiv läggs per vecka i `Skola-Rapporter/arkiv/`.

Länken skickas sedan:

```zsh
~/github/kg-elev-info/skill/scripts/imessage.sh "Veckorapport skolan v[WW]: [de 3 viktigaste raderna] — rapport: [LÄNK]"
```

- Mottagare: rad `MOTTAGARE=<telefonnummer eller Apple-ID>[,<nr2>...]` i elev.local (gitignored) — kommaseparerad lista. Alla får samma text.
- **Använd Dropbox-länkvarianten `?dl=0` (www.dropbox.com) i meddelandet** — renderas som snygg PDF-preview i webbläsaren/appen.
- Delningssteget misslyckas → rapportera fel, fortsätt med övriga steg; rapporten är redan på disk.
- Dropbox-token: keychain-post `skola-dropbox` (se utskrift-guider i share-report.sh vid fel). Exponera aldrig token — endast via keychain.

## 10. Kalibrering (när skrapet ser fel)

`harvest.mjs` är generisk fallback. Systemen är SPA-appar — vid ändrade UI:er:

1. Kör `recon.mjs` i tabben → läs `nav` (menylänkar) och `text`.
2. Använd `net <idx> 15` medan du klickar på UI:n för att upptäcka XHR/JSON API:er — överväg att anropa dem in-page (`fetch` kör med cookies) i stället för att peta i DOM.
   - **Blinda API-anrop** utan korrekta parametrar ger 500 (Skola24). Fånga alltid payload via `window.fetch`-hook i sidan — anropa aldrig blint.
3. Specialanpassa recepten i §5, kalendersync i §8 och delningen i §9 och notera ändringen i footer nedan.
4. Knockout-klick: native `el.click()` når ofta KO-bindningar ändå; annars `cdp.mjs click` (trusted input) eller navigera hash direkt: `#/<id från tile>`.

## 11. Frivillig schemaläggning

launchd/cron går inte automatiskt (BankID kräver människa). Föreslå fast rutin: måndag 07.30 kör användaren skillen när kaffet bryggs.

---

*Skapad: 2026-09-06. Live-kalibrerad 2026-09-06: cdp.mjs (eval/navigate/net/click, exit-bugg fixad), skola24-schema via UI-veckoväxlare (v.37–40 insamlade), infomentor rutter + kalendersub-app (`#calendarv2`), edlevo studieplan via menu-card, kalendersync via AppleScript mot iCloud-kalender (namn från elev.local; kalendern skapas manuellt under iCloud-rubriken eftersom make-new-calendar landar i On My Mac; EventKit-Swift plockades bort pga TCC-nekande för barr swift-process). Repot: `~/github/kg-elev-info` (publikt, github.com/gabrielpaues/kg-elev-info); skillen är symlinkad från opencode-configen. Kända luckor: Skola24:s ledighetsansöknings-accordion expanderas ej via JS-klick (kräver trusted click). Skola24-schema + infomentor-kalender korsrefereras i rapporten (avvikande skoldagar i båda).
Live-kalibrerad 2026-09-15 (v38–v44): (a) Infomentor-nyheter läses ur KO-VM (`ko.contextFor(el).$data` på `div[class*="__news-item__"] button.item-card`) — varken JS- eller trusted klick öppnar nyhetsdialogen; (b) kalenderrouten heter nu `#/communication/whole_week` (var `#/calendarv2/whole_week`); (c) skola24-schema-dagar.py kräver EN raw-fil med `weeks`-dict (en fil per vecka brast med "färre än 5 daghuvuden"); nutata: dict `v.NN` → `dagar[]`; (d) körklasser-evenemang ("ALLA körklasser") gäller eleven vid KORS1000X i schema/studieplan oavsett KAMMARKOR=false — kammarkören förblir separat; (e) halvveckorapport: körs skillen mån–fre läggs sektionen "I veckan som går (kvarvarande vN)" in ovanför Viktigt och dess poster kalendersyncas; (f) evals hålls korta (~10 s) — långa klicksekvenser tappar resultat mot shell-timeout; (g) mötesbokning kartlagd: `#/meeting` → "Du har inga bokade möten"/bokade möten. SAML-400-åtgärden (om navigering till service-URL) bekräftad fungerande utan nytt BankID. Parsern på nytt stabil v38–v40.
2026-09-15 kalendersync: calendar-sync.mjs fick lägena dump / apply-updates / remove — exakt dup-koll (summary + start) missar händelser som byter titel när mer info kommer (10 dubblettpar efter två körningar); matchmaking görs av AI mot en skriptfördumpad kalender, radering alltid efter användargodkänd uid-lista (skill §8 steg 2 och 4). AppleScript-isot-coercion (`«class isot» as text`) fungerar ej — datum formateras i scriptet (pad/iso-handlers; `number & text` ger mellanslag, coercera `as text` explicit). `whose … ≥ current date` mot iCloud är trögt (1–3 min); timeout 300 s. remove-läget har träffat stale-referenskrasch vid delete i materialiserad whose-lista — därför nytt uid-uppslag per rad + try-vakt, och "UID SAKNAS" = posten redan borta (ofarligt). Övning: en avbruten AppleScript-raderingskörning kan ha raderat MER än rapporterats — dumpa alltid på nytt och verifiera verkligt läge före upprepning.*
Live-kalibrerad 2026-10-04: tab-hantering i §3 ordnad — kolla list först, återanvänd/navigera om befintliga tabbar, öppna aldrig dubbletter; ett SAML-flöde åt gången. Skola24-tab fastnad i SAML-400 återloggades via omnavigering till stockholm.skola24.se utan nytt BankID (SMSESSION-kakan levde kvar). Edlevo: första laddningen efter tab-öppning misslyckas ofta (stale assertion/transaction) men omnavigering landar i inloggad startsida — samma recept; betrakta felet som transient, re-navigera i stället för att öppna ny tab (användare: "felskapar men funkar ändå").*
2026-10-04 räknestugor-feature: ny config-nycklar RAKNESTUGOR + RAKNESTUGOR_PLATSER i elev.local (§1) och nytt skript raknestugor.py (§6) — parsar mattecentrum.se/raknestugor/stockholm (serverrenderad HTML: `nav.tutoring-locations` med `<h2>` plats + `<span>` adress + `<h3>`-par dag/tid; stängd-notiser ur intro-richtext, t.ex. "Räknestugorna stängda v.44."). Matchning: skiftlägesokänslig exakt/in-under-sträng, difflib ≥0.84 rapporteras som osäker träff (fråga användaren, uppdatera config till exakt stavning — OBS: sidan stavar "Campus Viktor Rydberg" med k). Kalibrerat 2026-10-04: 21 platser parsade, Miriams tre platser matchade med korrekta tider; href är relativ → prefixas med domänen (inte sid-URL:n — dubbel-prefix-bugg fixad); notis-split på meningspunkt `\.\s+` så "v.44" (punkt följt av siffra) överlever. Sektionen syncas INTE till kalendern (återkommande, ej daterat).*
