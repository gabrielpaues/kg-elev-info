// Kör i tab: cat lib + system-extractor | cdp.mjs eval <idx> /tmp/x.js
// ... ej nödvändigt: denna fil är fristående och körs direkt.
// harvest.mjs — generisk text+datum-insamlare, funkar för alla tre system (v1, pre-kalibrering).

const host = location.hostname;
const system = host.includes('infomentor') ? 'infomentor'
  : host.includes('skola24') ? 'skola24'
  : host.includes('tieto') || host.includes('edlevo') ? 'edlevo' : 'okand';

const M = ['januari','februari','mars','april','maj','juni','juli','augusti','september','oktober','november','december'];
const M3 = ['jan','feb','mar','apr','maj','jun','jul','aug','sep','okt','nov','dec'];
const MON = new RegExp(`\\b(?:${[...M, ...M3].join('|')})\\s*(\\d{1,2})\\b`, 'i');
const DMY = /\b(\d{1,2})\/(\d{1,2})\b/;
const ISO = /\b(\d{4}-\d{2}-\d{2})\b/;
const WK = /\bv\.?\s?(\d{1,2})\b/i;

function normMonth(s) {
  const i = [...M, ...M3].findIndex((m) => s.toLowerCase().startsWith(m.slice(0, 3)));
  return i >= 0 ? String(i + 1).padStart(2, '0') : null;
}
function dateHint(text) {
  const mISO = text.match(ISO); if (mISO) return mISO[1];
  const mDMY = text.match(DMY);
  const mMON = text.match(MON);
  if (mMON) { const y = new Date().getFullYear(); return `${y}-${normMonth(mMON[0])}-${String(mMON[1]).padStart(2, '0')}`; }
  if (mDMY) { const y = new Date().getFullYear(); return `${y}-${String(mDMY[2]).padStart(2, '0')}-${String(mDMY[1]).padStart(2, '0')}`; }
  return null;
}

function findAncestor(el, pred) {
  let cur = el;
  for (let i = 0; i < 8 && cur && cur !== document.body; i++, cur = cur.parentElement) {
    if (pred(cur)) return cur;
  }
  return null;
}

const seen = new Set();
const items = [];
const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
let node;
while ((node = walker.nextNode())) {
  const txt = node.textContent.trim();
  if (txt.length < 6) continue;
  const hasDate = MON.test(txt) || DMY.test(txt) || ISO.test(txt) || WK.test(txt);
  if (!hasDate) continue;
  const block = findAncestor(node.parentElement,
    (e) => { const r = e.getBoundingClientRect(); return r.height > 24 && r.height < 600 && r.width > 200; }) || node.parentElement;
  const text = (block.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 400);
  const key = text.slice(0, 120);
  if (seen.has(key)) continue;
  seen.add(key);
  const link = block.querySelector ? block.querySelector('a[href]') : null;
  items.push({
    dateHint: dateHint(text),
    dateText: (text.match(MON) || [])[0] || (text.match(DMY) || [])[0] || (text.match(WK) || [])[0] || null,
    source: system,
    text,
    href: link ? link.href : null,
  });
}

// Full synlig text (trunkerad) för agentens egen analys
const raw = (document.body.innerText || '').replace(/\n{3,}/g, '\n\n').slice(0, 14000);

return {
  system, host, title: document.title, url: location.href,
  loggedIn: !/logga in|login|bankid|inloggning/i.test(document.body.innerText.slice(0, 3000)) || !!document.querySelector('nav, .navbar, [class*="dashboard"], [class*="menu"]'),
  items: items.slice(0, 120),
  raw,
};
