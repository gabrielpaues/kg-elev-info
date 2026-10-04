#!/usr/bin/env node
// Kalendersync: iCloud-kalender via AppleScript.
//
// Lägen:
//   node calendar-sync.mjs dump <ut-fil.json> [--från YYYY-MM-DD]
//       Läser alla events med start ≥ från (default: idag) → { events: [{uid, title, start, end, desc}] }. Skapar inget.
//   node calendar-sync.mjs apply-updates <updates.json>
//       updates.json: [{ uid, title?, date?, time?, endTime?, endDate?, allday?, desc? }]
//       Uppdaterar befintliga events in-place. Saknas tid fält lämnas tider orörda (skicka både start och slut vid flytt).
//   node calendar-sync.mjs remove <uids.json>
//       uids.json: ["uid1", "uid2"] eller { uids: [...] }. RADERAR events — kör bara efter att användaren
//       godkänt den konkreta uid-listan i chatten (samma regel som git-commit).
//   node calendar-sync.mjs <events.json>
//       Create-pass (idempotent): skapar events som saknar exakt match på summary + start date. Raderar inte, uppdaterar inte.
//
// events.json (create): { "events": [ { "date": "2026-09-10", "time": "09:00", "endTime": "12:00",
//                              "title": "Friluftsdag åk 1", "desc": "Källa: Skola24 v37" } ... ] }
// time/endTime valfria — utelämnas de sätts händelsen som heldag respektive 1 timme.
//
// Flöde med AI-dubletturval (se skill §8): dump → AI jämför proposals mot dumpen semantiskt → apply-updates
// (samnyttjad post uppdateras med ny titel/tid/desc) + ev. remove (godkänd lista) → create-pass som backstop.

import fs from 'node:fs';
import { execFileSync } from 'node:child_process';

const args = process.argv.slice(2);
const CAL = (() => {
  const k = args.indexOf('--kalender');
  if (k >= 0) return args[k + 1];
  try {
    const t = fs.readFileSync(process.env.HOME + '/github/kg-elev-info/data/elev.local', 'utf8');
    return t.match(/^KALENDER_NAMN=(.*)$/m)?.[1]?.trim() || null;
  } catch { return null; }
})() || 'Skola';
const pos = args.filter((a, i) => a && !a.startsWith('--') && args[i - 1] !== '--kalender');
const mode = pos[0];

const esc = (s) => String(s).replaceAll('\\', '\\\\').replaceAll('"', '\\"');
const TAB = String.fromCharCode(9);

// Gemensam AppleScript-prolog: mkDate-hjälp + kalendernamn.
const prolog = [
  'on mkDate(y, m, d, hh, mm)',
  '  set dt to current date',
  '  set day of dt to 1',
  '  set year of dt to y',
  '  set month of dt to m',
  '  set day of dt to d',
  '  set time of dt to hh * hours + mm * minutes',
  '  return dt',
  'end mkDate',
  'on pad(n)',
  '  if n < 10 then return "0" & n',
  '  return n as text',
  'end pad',
  'on iso(dt)',
  '  return ((year of dt) as text) & "-" & my pad(month of dt as integer) & "-" & my pad(day of dt) & "T" & my pad(hours of dt) & ":" & my pad(minutes of dt)',
  'end iso',
  'on nl2sp(t)',
  '  set AppleScript\'s text item delimiters to {linefeed, tab, return}',
  '  set parts to text items of t',
  '  set AppleScript\'s text item delimiters to " "',
  '  return parts as text',
  'end nl2sp',
  `set calName to "${esc(CAL)}"`,
  'tell application "Calendar"',
  `  set cals to every calendar whose name is calName`,
  '  if (count of cals) is 0 then return "SAKNAS: " & calName',
  '  set cal to item 1 of cals',
];

const run = (lines, keepTmp = false) => {
  const f = fs.mkdtempSync('/tmp/kalsync-') + '/kal.applescript';
  fs.writeFileSync(f, lines.join('\n'));
  try {
    const out = execFileSync('osascript', [f], { encoding: 'utf8', timeout: 300000 });
    if (out.startsWith('SAKNAS')) { console.error(out); process.exit(1); }
    return out;
  } catch (e) {
    console.error('skript sparad för felsökning:', f);
    throw e;
  }
};

// ---------- dump ----------
if (mode === 'dump') {
  const outFile = pos[1];
  if (!outFile) { console.error('användning: ... dump <ut-fil.json> [--från YYYY-MM-DD]'); process.exit(1); }
  const fr = (() => { const i = args.indexOf('--från'); return i >= 0 ? args[i + 1] : null; })();
  const [fy, fm, fd] = fr ? fr.split('-').map(Number) : [null, null, null];
  const cutoff = fy
    ? `my mkDate(${fy}, ${fm}, ${fd}, 0, 0)`
    : `(current date)`;
  const script = [
    ...prolog,
    `  set evs to (every event of cal whose start date ≥ ${cutoff})`,
    '  set out to {}',
    '  repeat with ev in evs',
    `    set end of out to (uid of ev) & "${TAB}" & (summary of ev) & "${TAB}" & my iso(start date of ev) & "${TAB}" & my iso(end date of ev) & "${TAB}" & my nl2sp((description of ev) as text)`,
    '  end repeat',
    '  set AppleScript\'s text item delimiters to linefeed',
    '  return (count of out) as text & linefeed & (out as text)',
    'end tell',
  ];
  const out = run(script);
  const [n, ...rows] = out.split('\n');
  const events = rows.filter(r => r.trim()).map(r => {
    const [uid, title, start, end, ...desc] = r.split(TAB);
    return { uid, title, start, end, desc: desc.join(TAB).trim() };
  });
  fs.writeFileSync(outFile, JSON.stringify({ kalender: CAL, hamtad: new Date().toISOString(), events }, null, 1));
  console.log(`dumpade ${events.length} (rapporterade ${n}) → ${outFile}`);
  process.exit(0);
}

// ---------- apply-updates ----------
if (mode === 'apply-updates') {
  const data = JSON.parse(fs.readFileSync(pos[1], 'utf8'));
  const ups = Array.isArray(data) ? data : data.updates;
  if (!Array.isArray(ups) || !ups.length) { console.error('inga updates i filen'); process.exit(1); }
  const lines = [...prolog];
  lines.push('  set msgs to {}');
  for (const u of ups) {
    if (!u.uid) { console.error('hoppar över (uid saknas):', JSON.stringify(u)); continue; }
    lines.push(`  set targets to (every event of cal whose uid is "${esc(u.uid)}")`);
    lines.push('  if (count of targets) > 0 then');
    lines.push('    set ev to item 1 of targets');
    if (u.title) lines.push(`    set summary of ev to "${esc(u.title)}"`);
    if (u.desc !== undefined) lines.push(`    set description of ev to "${esc(u.desc)}"`);
    if (u.date) {
      const s = u.allday ? '00:00' : (u.time || '00:00');
      const end = u.endDate
        ? { d: u.endDate, t: u.endTime || '23:59' }
        : u.endTime ? { d: u.date, t: u.endTime }
        : u.allday ? { d: u.date, t: '23:55' }
        : null;
      // End först — att flytta start framåt medan gammal end ligger kvar triggar "start must be before end"
      lines.push(`    set end date of ev to my mkDate(${end.d.split('-').map(Number).join(', ')}, ${end.t.replace(':', ', ')})`);
      lines.push(`    set start date of ev to my mkDate(${u.date.split('-').map(Number).join(', ')}, ${s.replace(':', ', ')})`);
      if (u.allday) lines.push('    set allday event of ev to true');
    }
    lines.push('  else');
    lines.push(`    log "UID SAKNAS: ${esc(u.uid)}"`);
    lines.push(`    set end of msgs to "UID SAKNAS: ${esc(u.uid)}"`);
    lines.push('  end if');
  }
  lines.push('end tell');
  lines.push('set AppleScript\'s text item delimiters to linefeed');
  lines.push('return ("fel: " & (count of msgs) as text) & linefeed & (msgs as text)');
  const res = run(lines);
  console.log(`apply-updates på ${CAL}):\n${res.trim()}`);
  process.exit(0);
}

// ---------- remove ----------
if (mode === 'remove') {
  const raw = JSON.parse(fs.readFileSync(pos[1], 'utf8'));
  const uids = Array.isArray(raw) ? raw : raw.uids;
  if (!Array.isArray(uids) || !uids.length) { console.error('inga uids i filen'); process.exit(1); }
  const lines = [...prolog];
  lines.push('  set msgs to {}');
  lines.push('  set num to 0');
  lines.push(`  set total to ${uids.length}`);
  for (const uid of uids) {
    lines.push(`  set targets to (every event of cal whose uid is "${esc(uid)}")`);
    lines.push(`  if (count of targets) > 0 then`);
    lines.push(`    try`);
    lines.push(`      set ev to item 1 of targets`);
    lines.push(`      set end of msgs to "RADERAR: " & (summary of ev)`);
    lines.push(`      delete (first event of cal whose uid is "${esc(uid)}")`);
    lines.push(`      set num to num + 1`);
    lines.push(`    on error eM`);
    lines.push(`      set end of msgs to "FEL: " & eM`);
    lines.push('    end try');
    lines.push('  else');
    lines.push(`    set end of msgs to "UID SAKNAS: ${esc(uid)}"`);
    lines.push('  end if');
  }
  lines.push('end tell');
  lines.push('set AppleScript\'s text item delimiters to linefeed');
  lines.push('return ("raderade " & num as text) & " / " & total & linefeed & (msgs as text)');
  const res = run(lines);
  console.log(`remove på ${CAL}):\n${res.trim()}`);
  process.exit(0);
}

// ---------- create (default) ----------
if (!fs.existsSync(String(mode))) { console.error(`fil saknas: ${mode}`); process.exit(1); }
const data = JSON.parse(fs.readFileSync(mode, 'utf8'));
const events = data.events || [];

const D = (iso, hhmm) => {
  const [y, m, d] = iso.split('-').map(Number);
  return `{y:${y}, m:${m}, d:${d}} + "${hhmm || '00:00'}"`;
};
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

// Prologen innehåller redan set calName + tell + set cal — lägg inte till ett nytt tell-block
const lines = [...prolog, 'set numCreated to 0', 'set numSkipped to 0'];
for (const e of events) {
  if (!e.date || !e.title) { console.error('hoppar över (kräver date + title):', JSON.stringify(e)); continue; }
  const s = mkDate(e.date, e.allday ? '00:00' : e.time);
  const t = mkEnd(e);
  const title = esc(e.title);
  const desc = esc(e.desc || '');
  const allDay = e.allday ? 'allday event:true, ' : '';
  lines.push(`  set dupCheck to (count of (every event of cal whose summary is "${title}" and start date is ${s}))`);
  lines.push(`  if dupCheck is 0 then`);
  lines.push(`    make new event in cal with properties {summary:"${title}", start date:${s}, end date:${t}, ${allDay}description:"${desc}"}`);
  lines.push(`    set numCreated to numCreated + 1`);
  lines.push(`  else`);
  lines.push(`    set numSkipped to numSkipped + 1`);
  lines.push(`  end if`);
}
lines.push('end tell');
lines.push('return (numCreated as text) & " skapade, " & (numSkipped as text) & " hoppade över"');
const out = run(lines);
console.log(`Kalender "${CAL}"): ${out.trim()}`);
