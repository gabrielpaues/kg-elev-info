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
  Kungsholmens gymnasium, kg-elev-info.
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

Format:

```
ELEV_NAMN=<förnamn>
KLASS=<XxNNxx>
ARSKURS=<1-3>
KAMMARKOR=<true|false>
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

```zsh
C=~/github/kg-elev-info/skill/scripts/cdp.mjs
node $C new "https://sso.infomentor.se/login.ashx?idp=stockholm_par"
node $C new "https://stockholm.skola24.se"
node $C new "https://education.service.tieto.com/WE.Education.Spaces/Start?Actor=Actor_Relative&idpMethod=SAML&domain=StockholmEdu"
node $C list
```

Loggas redan in (sessioner lever) → hoppa till steg 4.

## 4. Vänta på BankID-inloggning

Säg till användaren: *logga in i de tre Chrome-fönstren (Infomentor, Skola24, Edlevo) — säg till när klart.* Vänta på bekräftelse, verifiera därefter:

```zsh
node $C eval <infomentor-idx> ~/github/kg-elev-info/skill/scripts/recon.mjs
```

`loggedInGuess: false` eller loginformulär i text → fråga igen. Fortsätt aldrig på osäker inloggning.

**⚠️ Kalibreringslektion 2026-09-06:**
- Kör bara **en SAML-inloggning i taget**. Tre parallella flöden i samma Siteminder-session → assertionen expirerar → `HTTP 400 Bad Request` på `saml2sso?SMASSERTIONREF=QUERY`. Åtgärd: navigera om tabben till service-URL:en — ofta lever SMSESSION-kakan kvar och inloggningen sker utan nytt BankID.
- Skola24 kan svara 500 vid blind re-spel av API:er (saknade params) — kör bara sidans egna UI-flöden.

## 5. Skrapa alla tre (kalibrerade recept 2026-09-06)

Spara rå JSON per system i `~/github/kg-elev-info/raw/YYYY-MM-DD-<system>.json>`. Råtext är sanningens källa — inget i rapporten får komma från annat än dessa data + terminsdatum.

Cdp-kommandon: `list | new <url> | navigate <idx> <url> | eval <idx> <fil.js> | click <idx> <css-sel> | net <idx> <sek> | close <idx>`. `eval`-filer får vara fristående (top-nivå `return` omsluts av `(async()=>{...})()`); `await` och `setTimeout` är OK. **JS-klick fungerar inte i Infomentor/KO — använd `click` (trusted CDP-input) eller `element.closest('a.tile').click()` via JS.**

### 4a. Infomentor (hub.infomentor.se, Knockout-SPA)

Direkta hash-ruter (navigera med `$C navigate <idx> "https://hub.infomentor.se/#/communication/news"`):

| Ruta | Innehåll |
|------|----------|
| `#/communication/news` | NYHETER — titel + av + datum; klicka rad (JS) för brödtext |
| `#/communication/links` | LÄNKAR-tabellen (namn/beskrivning/url) |
| `#/communication/files` | nya filer (namn/datum/storlek) |
| `#/communication/consent` | SAMTYCKEN — kontrollera "Inga aktiva samtycken" |
| `#/` | tiles + NOTISER-panel (punktlista med datum, t.ex. "Nyhet publicerad 26-08-26") |

Kalender: sub-app med egen router. Navigera `#/`, JS: `document.querySelector('#calendarv2').closest('a.tile').click()`, vänta 4 s, landar på `#/calendarv2/whole_week`. Loopa veckor: `aria-label="Nästa vecka"`-knapp, 2,5 s per vecka. Klipp text: från `Vecka NN` till `NOTISER`. Innehåll: skoldagstyper (Gul heldag/eftermiddag/förmiddag med tider = avvikande skoldag!), prov/inlämningar (Examinationsschema), temadagar, elevhälsa.

Guld i kalendern: raden "Gul heldag"/"Gul eftermiddag" betyder förkortad/avvikande skoldag → both schema-avvikelse och praktisk planering.

Mötesbokning (`#/meeting`): kan behövas för utvecklingssamtal — kolla om öppna bokningsfönster finns; om texten visar aktiva perioder, rapportera under Åtgärda.

### 4b. Skola24 (websthlm.skola24.se)

| URL | Innehåll |
|-----|----------|
| `/portal/start` | portalmeny (Schemavisare, Elev/Klass-bild, Anmäla frånvaro, Ansöka om ledighet) |
| `/portal/start/absence/leave-application` | ledighetsansökningar — "Visa ledighetsansökningar" är accordion, expanderas inte via JS-klick; låt användaren kolla manuellt eller använd `$C click 0 "h2"` — OBS: kräver trusted click |
| Schemavisare → veckor | se recept nedan |

Schema-recept:
1. Navigera tabben till Schemavisare (JS-klick på länken funkar) → `/portal/start/timetable/timetable-viewer/stockholm.skola24.se/`.
2. Öppna veckodropdown: JS-klick på `button.w-arrow` med `aria-label="Tryck för att öppna meny"`, 0,9 s.
3. Klicka vecka: `[...document.querySelectorAll('a')].find(a => a.innerText.trim().startsWith('v.38 '))`, 3 s.
4. Klipp: från `'Visa schema för'` till `'Senast publicerad'` i `document.body.innerText`. Sista raden = senaste publiceringstid (rapportera den!).

Schema-texten innehåller: dagar (Måndag 7/9 …), lektioner (kurskod, lärarinitialer, rumsnr) och specialraderna under veckan: "10/9, 9:00-12:00 Friluftsdag", "Studiedag", "9/9, 12:30-17:00 Studieeftermiddag" — dessa är guld, korsrefer­era med Infomentor-kalendern.

**Strukturerad parsing per dag (krav för start/sluttider + idrottsdagar):**

```zsh
python3 ~/github/kg-elev-info/skill/scripts/skola24-schema-dagar.py ~/github/kg-elev-info/raw/<datum>-skola24-schema.json > ~/github/kg-elev-info/raw/<datum>-skola24-dagar.json
```

- Ger per dag: datum, start (första lektion), slut (sista lektion), lektioner med kurs/tid/sal/lärare, händelser, `idrott`-flagga (IDRO-kod).
- Validering inbyggd: dagarna splittas via tidsminskning i tidflödet + krav att lektionsantal == tidpar per dag. Returnerar `fel` → rapportera dagen som "fördelning osäker" — hitta ALDRIG på fördelning.
- Empiriskt stabil på v37–v40 2026-09-06. Om Skola24 ändrar rendering: kör recon + kalibrera (se §10). Live-DOM-extraktion per dagkolumn är den robusta uppgraderingen om flat-parsningen briserar.

### 4c. Edlevo (education.service.tieto.com)

Startsidan listar `div.menu-card` (Barnomsorgsansökan, Familjeförhållanden, Registrera inkomst, Studieplan …). Studieplan: JS-klick på card med texten "Studieplan" → ny sida `USStudyPlanGuardian?childId=...` med tabeller: Planerade / Pågående / Avslutade + Studieplansanteckningar. Dumpa hela (kurser med poäng, perioder, betyg). Betyg spelar roll först vid avslutade kurser; pågående = läsårets plan. Kolla inför utvecklingssamtal.

## 6. Hämta publika terminsdatum + konserter

```zsh
python3 ~/github/kg-elev-info/skill/scripts/hamta-lasaret.py ~/github/kg-elev-info/data/lasaret-datum.md
```

Skriptet hämtar ALLA terminssektioner strukturellt ((Höst|Vår)terminen ÅÅÅÅ) — robust när skolan byter läsår eller plockar bort höstterminen. Tidigare sed-kommando på rå HTML brast på båda punkterna (tag-soppa + försvunnen höstterminssektion → tomt resultat). Kör ALLTID scriptet, aldrig sed på HTML.

**Konserter** (Kungsholmens är också Stockholms musikgymnasium — eleven deltar i körkonserter):

```zsh
python3 ~/github/kg-elev-info/skill/scripts/konserter.py --klass <KLASS>
```

- `KLASS` läses från `data/elev.local`. Om den är tom: hitta klasskoden i Infomentor-kalendern (t.ex. "XxNNxx LÄRARE inlämning" / "Sv1 XXNNXX Prov") — mönstret `\b[NS][a-z]\d{2}[a-z]{2}\b`, välj den som återkommer i elevens poster. Årskurs härleds ur koden (NN = antagningsår); verifiera mot Edlevo-kurslistan (enstaka Nivå 1-kurser = åk 1) och skriv in i elev.local.
- Filtreringen matchar: (a) klasskoden utskriven bland medverkande, (b) "hela årskurs N", (c) hela skolan — MEN BARA om ingen specifik grupp (annan klass/årskurs) nämns (bug: "Årskurs 3 från skolan" matchade felaktigt "hela skolan" tidigare).
- Kammarkören är separat antagen — anta ALDRIG att eleven sjunger där. `KAMMARKOR=true/false` i elev.local styr: false → exkludera kammarkörens konserter utan vidare kontroll; true → inkludera dem. Saknas värdet → fråga användaren en gång och skriv in det.
- Konsertbiljetter med datum för biljettsläpp → går under "Åtgärda i förväg" om släppet ligger inom rapportperioden, annars under "Framåt".

## 7. Bygg rapport

Spara som `~/github/kg-elev-info/rapporter/YYYY-MM-DD-vecka-<WW>.md` (veckonummer = kommande vecka, programmatiskt: `date -v+1w +%V`).

```markdown
# Veckorapport — Kungsholmens gymnasium
Vecka [WW], [mån dd]–[sön dd]. Sammanställd [YYYY-MM-DD].

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
- Att-göra-ägare:rapporten vänder sig till användaren (vårdnadshavare) — formulera åtgärder som "bolja utvecklingssamtal", inte "kontakta mentorn" utan anledning.
- Veckodag ALLTID programmatiskt från datum (`date -j -f "%Y-%m-%d" ... +%A` eller python). Aldrig härledas från minne.
- Osäker tolkning av raw-text → lista under "Framåt" med källcitat, aldrig som säker händelse med falsk precision.
- Ifylld frånvaro/betyg som verkar gammalt → inte i veckas sektioner; Checka datum i texten.
- Tomma sektioner får aldrig hoppas över.
- Skrivregler enligt AGENTS.md (ingen inflation, inga påhittade datum, neutral ton).
- Avsluta svaret till användaren med rapportens sökväg + de 3 viktigaste raderna, inte hela rapporten i chatten.

## 8. Kalendersync (iCloud, delad med eleven)

**Kalendern (namn från `KALENDER_NAMN` i elev.local) MÅSTE ligga under iCloud-kontot.** AppleScript exponerar inte konton och `make new calendar` landar i default-kontot (oftast On My Mac) — skapa därför kalendern engångsvis manuellt: Cal.app → högerklicka **iCloud-rubriken** i sidofältet → Ny kalender → namnet från KALENDER_NAMN. Skriptet fyller däremot events via AppleScript obehindrat (osascript har egen behörighet; EventKit-via-Swift nekades TCC i denna miljö, försök ej igen).

Efter rapporten: bygg `~/github/kg-elev-info/data/kalender-events.json` av rapportens daterade poster (Viktigt kommande vecka, Schema-avvikelser, Framåt — provisioner, avvikelser, prov, inlämningar, lov). Syntax:

```json
{ "events": [
  { "date": "2026-09-10", "time": "09:00", "endTime": "12:00", "title": "Friluftsdag åk 1", "desc": "Källa + vad som gäller" },
  { "date": "2026-10-26", "endDate": "2026-10-30", "endTime": "23:59", "allday": true, "title": "Höstlov" }
] }
```

```zsh
node ~/github/kg-elev-info/skill/scripts/calendar-sync.mjs ~/github/kg-elev-info/data/kalender-events.json
```

- Kalender: namnet kommer från `KALENDER_NAMN` i elev.local (scriptet skapar den om den saknas — kontrollera då att den hamnar i iCloud, inte On My Mac). Idempotent — varje körning skapar bara nya poster (dup-check på summary + start date), raderar aldrig.
- Håltdagar utan känd tid: `allday: true`; lö och lov: `endDate`.
- Endast daterade saker → kalendern. Vaga uppgifter ("kolla mentorns info") hamnar bara i rapporten.
- Delning med elevens/familjens Apple ID: görs endast manuellt i Cal.app (delningsknapp) — kan ej skriptas.

## 9. Dela rapporten (Dropbox-länk + iMessage)

Efter rapporten + kalendersync (§8):

```zsh
~/github/kg-elev-info/skill/scripts/share-report.sh ~/github/kg-elev-info/rapporter/<rapport>.md
```

Flödet: MD → stilad HTML (`md2html.py`) → PDF (debug-Chrome, `cdp.mjs pdf`) → Dropbox `Skola-Rapporter/rapport-senaste.pdf` (mode=overwrite → **länken är beständig mellan veckor**) → delbar länk → skrivs till `data/last-delad-lank.txt` + stdout (direktläsning `dl.dropboxusercontent.com` också). Arkiv läggs per vecka i `Skola-Rapporter/arkiv/`.

Länken skickas sedan:

```zsh
~/github/kg-elev-info/skill/scripts/imessage.sh "Veckorapport skolan v[WW]: [de 3 viktigaste raderna] — rapport: [LÄNK]"
```

- Mottagare: rad `MOTTAGARE=<telefonnummer eller Apple-ID>[,<nr2>...]` i elev.local (gitignored) — kommaseparerad lista. Alla får samma text.
- **Använd Dropbox-länkvarianten `?dl=0` (www.dropbox.com) i meddelandet** — renderas som snygg PDF-preview i webbläsaren/appen.
- Delningssteget misslyckas → rapportera fel, fortsätt med övriga steg; rapporten är redan på disk.
- Dropbox-token: keychain-post `skola-dropbox` (se utskrift-guider i share-report.sh vid fel). Ge ALDRIG ut token rumsligt — bara via keychain.

## 10. Kalibrering ( när skrapet ser fel)

`harvest.mjs` är generisk fallback. Systemen är SPA-appar — vid ändrade UI:er:

1. Kör `recon.mjs` i tabben → läs `nav` (menylänkar) och `text`.
2. Använd `net <idx> 15` medan du klickar på UI:n för att upptäcka XHR/JSON API:er — överväg att anropa dem in-page (`fetch` kör med cookies) i stället för att peta i DOM.
   - **Spärr på retrier**: blinda API-anrop utan korrekta parametrar ger 500 (Skola24). Fånga ALLTID payload via `window.fetch`-hook i sidan och replaya aldrig blint.
3. Specialanpassa recepten i §5, kalendersync i §8 och delningen i §9 och notera ändringen i footer nedan.
4. Knockout-klick: native `el.click()` når ofta KO-bindningar ändå (se im2-information som fungerade); annars `cdp.mjs click` (trusted input) eller navigera hash direkt: `#/<id från tile>`.

## 11. Frivillig schemaläggning

launchd/cron går inte automatiskt (BankID kräver människa). Föreslå låst rutin: måndag 07.30 kör användaren skillen när kaffet bryggs.

---

*Skapad: 2026-09-06. Live-kalibrerad 2026-09-06: cdp.mjs (eval/navigate/net/click, exit-bugg fixad), skola24-schema via UI-veckoväxlare (v.37–40 insamlade), infomentor rutter + kalendersub-app (`#calendarv2`), edlevo studieplan via menu-card, kalendersync via AppleScript mot iCloud-kalender (namn från elev.local; kalendern skapas manuellt under iCloud-rubriken eftersom make-new-calendar landar i On My Mac; EventKit-Swift plockades bort pga TCC-nekande för bare swift-process). Repot flyttat till `~/github/kg-elev-info` (privat GitHub-profil gabrielpaues); skillen är symlinkad från config-katalogen. Kända luckor: Skola24 ledighetsansöknings-accordion expanderas ej via JS-klick (kräver trusted click), Infomentor mötesbokning ej än kartlagd. Skola24-schema + infomentor-kalender korsrefereras i rapporten (avvikande skoldagar i båda).*
