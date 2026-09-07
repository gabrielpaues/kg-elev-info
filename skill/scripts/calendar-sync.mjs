#!/usr/bin/env node
// Kalendersync: läser events-JSON och skapar iCloud-kalenderhändelser via AppleScript.
// Idempotent: skrivning sker bara om event med samma summary + start date saknas.
//
// Användning:
//   node calendar-sync.mjs <events.json> [--kalender "Skola - <namn>"]
//
// events.json: { "events": [ { "date": "2026-09-10", "time": "09:00", "endTime": "12:00",
//                              "title": "Friluftsdag åk 1", "desc": "Källa: Skola24 v37" } ... ] }
// time/endTime valfria (heldagsexempel: "07:00"–"22:00" markeras ej — anges direkt).

import fs from 'node:fs';

const [file, ...rest] = process.argv.slice(2);
const komSwitch = rest.indexOf('--kalender');
// Kalendernamn: --kalender > elev.local (KALENDER_NAMN) > generiskt "Skola"
function calFrånKonfig() {
  try {
    const t = fs.readFileSync(process.env.HOME + '/github/kg-elev-info/data/elev.local', 'utf8');
    return t.match(/^KALENDER_NAMN=(.*)$/m)?.[1]?.trim() || null;
  } catch { return null; }
}
const CAL = komSwitch >= 0 ? rest[komSwitch + 1] : (calFrånKonfig() || 'Skola');

if (!file) { console.error('användning: calendar-sync.mjs <events.json>'); process.exit(1); }
const data = JSON.parse(fs.readFileSync(file, 'utf8'));
const events = data.events || [];

const esc = (s) => String(s).replaceAll('\\', '\\\\').replaceAll('"', '\\"');
const D = (iso, hhmm) => {
  const [y, m, d] = iso.split('-').map(Number);
  return `{y:${y}, m:${m}, d:${d}} + "${hhmm || '00:00'}"`;
};
// AppleScript: bygg date via fält (locale-oberoende)
const mkDate = (iso, hhmm) => {
  const [y, m, dd] = iso.split('-').map(Number);
  const [t, mi] = (hhmm || '00:00').split(':').map(Number);
  return `my mkDate(${y}, ${m}, ${dd}, ${t}, ${mi})`;
};
const mkEnd = (e) => {
  if (e.endDate) return mkDate(e.endDate, e.endTime || '23:59');
  if (e.endTime) return mkDate(e.date, e.endTime);
  if (e.allday) return mkDate(e.date, '23:55');
  return `(${mkDate(e.date, e.time)} + 1 * hours)`;
};

const lines = [];
lines.push('on mkDate(y, m, d, hh, mm)');
lines.push('  set dt to current date');
lines.push('  set day of dt to 1');
lines.push('  set year of dt to y');
lines.push('  set month of dt to m');
lines.push('  set day of dt to d');
lines.push('  set time of dt to hh * hours + mm * minutes');
lines.push('  return dt');
lines.push('end mkDate');
lines.push(`set calName to "${esc(CAL)}"`);
lines.push('set numCreated to 0');
lines.push('set numSkipped to 0');
lines.push('tell application "Calendar"');
lines.push(`  if not (exists calendar calName) then make new calendar with properties {name:calName}`);
lines.push(`  set cal to calendar calName`);

const itemLines = [];
for (const e of events) {
  if (!e.date || !e.title) { console.error('hoppar över (kräver date + title):', JSON.stringify(e)); continue; }
  const s = mkDate(e.date, e.allday ? '00:00' : e.time);
  const t = mkEnd(e);
  const title = esc(e.title);
  const desc = esc(e.desc || '');
  const allDay = e.allday ? 'allday event:true, ' : '';
  itemLines.push(`  set dupCheck to (count of (every event of cal whose summary is "${title}" and start date is ${s}))`);
  itemLines.push(`  if dupCheck is 0 then`);
  itemLines.push(`    make new event in cal with properties {summary:"${title}", start date:${s}, end date:${t}, ${allDay}description:"${desc}"}`);
  itemLines.push(`    set numCreated to numCreated + 1`);
  itemLines.push(`  else`);
  itemLines.push(`    set numSkipped to numSkipped + 1`);
  itemLines.push(`  end if`);
}
lines.push(...itemLines);
lines.push('end tell');
lines.push('return (numCreated as text) & " skapade, " & (numSkipped as text) & " hoppade över"');

const os = fs.mkdtempSync('/tmp/kalsync-') + '/kal.applescript';
fs.writeFileSync(os, lines.join('\n'));
import('node:child_process').then(({ execFileSync }) => {
  try {
    const out = execFileSync('osascript', [os], { encoding: 'utf8', timeout: 120000 });
    console.log(`Kalender "${CAL}"):`, out.trim());
  } catch (e) {
    console.error('osascript-fel:', e.stderr || e.message);
    console.error('Tips: ge Terminal/opencode tillgång till Kalender (Systeminställningar → Sekretess → Automation), och kontrollera att kalendern landar under iCloud-kontot.');
    process.exit(1);
  }
});
