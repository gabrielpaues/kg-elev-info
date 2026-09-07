#!/usr/bin/env node
// Generic Chrome DevTools Protocol client. Zero dependencies (Node >= 22, global fetch + WebSocket).
// Usage:
//   cdp.mjs list                      — list tabs (index, title, url)
//   cdp.mjs new <url>                 — open new tab, print index
//   cdp.mjs navigate <idx> <url>      — navigate tab to url
//   cdp.mjs eval <idx> <file>         — evaluate JS file in tab (async ok), print JSON result
//   cdp.mjs net <idx> <seconds>       — log network request URLs for N seconds (recon)
//   cdp.mjs close <idx>               — close tab

const PORT = process.env.CDP_PORT || 9222;
const base = `http://127.0.0.1:${PORT}`;

async function targets() {
  const r = await fetch(`${base}/json`, { signal: AbortSignal.timeout(5000) });
  if (!r.ok) throw new Error(`CDP ${r.status}. Är Chrome startad med --remote-debugging-port=${PORT}?`);
  return (await r.json()).filter((x) => x.type === 'page');
}

async function ws(url) {
  const sock = new WebSocket(url);
  await new Promise((res, rej) => {
    sock.addEventListener('open', res, { once: true });
    sock.addEventListener('error', () => rej(new Error('ws connect failed')), { once: true });
  });
  const pending = new Map();
  const handlers = new Set();
  let nextId = 1;
  sock.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { res, rej } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
    } else {
      handlers.forEach((h) => h(msg));
    }
  });
  return {
    call: (method, params = {}) => new Promise((res, rej) => {
      const id = nextId++;
      pending.set(id, { res, rej });
      sock.send(JSON.stringify({ id, method, params }));
    }),
    onEvent: (h) => handlers.add(h),
  };
}

const [cmd, arg1, arg2] = process.argv.slice(2);

// referenser: N = positionellt index (instabil!) | id:XXXX = stabil tab-id | sträng = match i url/titel
async function pick(ref) {
  const ts = await targets();
  const s = String(ref);
  if (s.startsWith('id:')) {
    const t = ts.find((x) => x.id === s.slice(3));
    if (!t) throw new Error('ingen tabb med id ' + s);
    return t;
  }
  if (/^\d+$/.test(s)) return ts[Number(s)];
  const t = ts.find((x) => x.url.includes(s) || x.title.includes(s));
  if (!t) throw new Error('ingen tabb matchar ' + s);
  return t;
}

try {
  if (cmd === 'list') {
    (await targets()).forEach((x, i) => console.log(`[${i}] id:${x.id} ${x.title}\n    ${x.url}`));
  } else if (cmd === 'new') {
    const r = await fetch(`${base}/json/new?${encodeURIComponent(arg1)}`, { method: 'PUT' });
    const t = await r.json();
    console.log(`id:${t.id}`);
  } else if (cmd === 'navigate') {
    const t = await pick(arg1);
    const c = await ws(t.webSocketDebuggerUrl);
    await c.call('Page.navigate', { url: arg2 });
    console.log('ok');
    process.exit(0);
  } else if (cmd === 'eval') {
    const t = await pick(arg1);
    const c = await ws(t.webSocketDebuggerUrl);
    const expr = (await import('node:fs')).promises;
    const body = await expr.readFile(arg2, 'utf8');
    const r = await c.call('Runtime.evaluate', {
      expression: `(async () => { ${body}\n })()`,
      awaitPromise: true, returnByValue: true, userGesture: true,
    });
    if (r.exceptionDetails) {
      console.error(JSON.stringify({ error: r.exceptionDetails.exception?.description || r.exceptionDetails.text }, null, 2));
      process.exit(1);
    }
    console.log(JSON.stringify(r.result.value, null, 2));
    process.exit(0);
  } else if (cmd === 'net') {
    const t = await pick(arg1);
    const c = await ws(t.webSocketDebuggerUrl);
    await c.call('Network.enable', {});
    const seen = new Set();
    c.onEvent((msg) => {
      if (msg.method !== 'Network.requestWillBeSent') return;
      const u = msg.params.request.url;
      if (!seen.has(u)) { seen.add(u); console.log(msg.params.type || '?', u); }
    });
    await new Promise((r) => setTimeout(r, (Number(arg2) || 10) * 1000));
    process.exit(0);
  } else if (cmd === 'pdf') {
    const t = await pick(arg1);
    const c = await ws(t.webSocketDebuggerUrl);
    let buf = null;
    for (let försök = 1; försök <= 4; försök++) {
      const r = await c.call('Page.printToPDF', { printBackground: true, marginTop: 0.4, marginBottom: 0.4, marginLeft: 0.3, marginRight: 0.3 });
      buf = r.data ? Buffer.from(r.data, 'base64') : null;
      if (buf && buf.length > 100 && buf.subarray(0, 5).toString() === '%PDF-') break;
      // omdata + nytt försök (layout kan inte vara klar än efter navigate)
      await c.call('Page.reload', { ignoreCache: true }).catch(() => {});
      await new Promise((res) => setTimeout(res, 2500 * försök));
    }
    if (!buf || buf.length === 0 || buf.subarray(0, 5).toString() !== '%PDF-') throw new Error('printToPDF gav inget giltigt PDF-dokument efter 4 försök');
    await (await import('node:fs')).promises.writeFile(arg2, buf);
    console.error('pdf-info: bytes=' + buf.length);
    console.log('pdf → ' + arg2);
    process.exit(0);
  } else if (cmd === 'click') {
    const t = await pick(arg1);
    const c = await ws(t.webSocketDebuggerUrl);
    await c.call('DOM.enable', {});
    const doc = await c.call('DOM.getDocument', {});
    const node = await c.call('DOM.querySelector', { nodeId: doc.root.nodeId, selector: arg2 });
    if (!node.nodeId) throw new Error('matchar inget: ' + arg2);
    const box = await c.call('DOM.getBoxModel', { nodeId: node.nodeId });
    const q = box.model.content;
    if (!q) throw new Error('osynligt element: ' + arg2);
    const cx = Math.round((q[0] + q[4]) / 2), cy = Math.round((q[1] + q[5]) / 2);
    await c.call('Input.dispatchMouseEvent', { type: 'mousePressed', x: cx, y: cy, button: 'left', clickCount: 1 });
    await c.call('Input.dispatchMouseEvent', { type: 'mouseReleased', x: cx, y: cy, button: 'left', clickCount: 1 });
    console.log(`click ${cx},${cy}`);
    process.exit(0);
  } else if (cmd === 'close') {
    const t = await pick(arg1);
    await fetch(`${base}/json/close/${t.id}`);
    console.log('ok');
  } else {
    console.log('kommandon: list | new <url> | navigate <idx> <url> | eval <idx> <file> | net <idx> <sek> | close <idx>');
  }
} catch (e) {
  console.error('FEL:', e.message);
  process.exit(1);
}
