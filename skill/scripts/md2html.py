#!/usr/bin/env python3
"""md → fin standalone-HTML för rapporten. Endast stdlib; stöder delmängden som rapporttemplate använder:
rubriker (#/##), stycken, fetstil (**x**), listor (- item), numrerade listor, tabeller (| a | b |), HR (---).
"""
import html
import re
import sys

SRC, DST = sys.argv[1], sys.argv[2]
text = open(SRC, encoding="utf-8").read()

CSS = """
:root { --ink:#1a2433; --accent:#0b5cff; --soft:#6b7688; --line:#e3e8ef; --bg:#f6f8fb; }
* { box-sizing:border-box; }
body { font:16px/1.65 -apple-system, "Helvetica Neue", Georgia, serif; color:var(--ink);
       background:var(--bg); margin:0; padding:0; }
main { max-width:680px; margin:0 auto; padding:28px 20px 64px; }
header.top { background:linear-gradient(135deg,#0b2a5b,#0b5cff); color:#fff; padding:40px 20px 34px; }
header.top .wrap { max-width:680px; margin:0 auto; }
header.top h1 { font-size:26px; margin:0 0 6px; letter-spacing:-.02em; }
header.top p { margin:0; opacity:.85; font-size:14px; }
h2 { font-size:19px; margin:34px 0 10px; padding-bottom:6px; border-bottom:2px solid var(--accent); }
h3 { font-size:16px; margin:22px 0 8px; color:var(--accent); }
ul, ol { padding-left:22px; margin:8px 0 14px; }
li { margin:5px 0; }
table { border-collapse:collapse; width:100%; margin:12px 0 18px; font-size:14.5px; background:#fff; }
th { text-align:left; background:#eef2f8; }
th, td { padding:8px 10px; border:1px solid var(--line); vertical-align:top; }
td:first-child, th:first-child { white-space:nowrap; }
strong { font-weight:650; }
p { margin:10px 0; }
hr { border:0; border-top:1px solid var(--line); margin:26px 0; }
footer { color:var(--soft); font-size:12.5px; margin-top:40px; border-top:1px solid var(--line); padding-top:12px; }
.card { background:#fff; border:1px solid var(--line); border-radius:10px; padding:6px 18px 10px; margin:14px 0; box-shadow:0 1px 2px rgba(10,30,60,.05); }
@media (prefers-color-scheme: dark) { :root { --ink:#e8ecf2; --soft:#9aa4b2; --line:#2a3342; --bg:#12161d; }
  table, .card { background:#191f29; } th { background:#1f2733; } }
""".strip()


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\w)(https?://[^\s\)]+)", r'<a href="\1">\1</a>', s)
    s = re.sub(r"(?<![\w/])\b([wW]w\d{1,2})\b", r"<span class='wk'>\1</span>", s)
    return s


blocks, card = [], False
lines = text.splitlines()
i, first_h1 = 0, True
while i < len(lines):
    ln = lines[i].rstrip()
    if first_h1 and ln.startswith("# "):
        blocks.append(f"<h1>{inline(ln[2:])}</h1>".replace("<h1>", "T01<h1>", 1))
        first_h1 = False
        i += 1
        continue
    if ln.startswith("## "):
        blocks.append(f"<h2>{inline(ln[3:])}</h2>")
    elif ln.startswith("### "):
        blocks.append(f"<h3>{inline(ln[4:])}</h3>")
    elif ln.strip() == "---":
        blocks.append("<hr>")
    elif ln.startswith("| ") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
        rows = []
        while i < len(lines) and lines[i].startswith("|"):
            i += 1
            if re.match(r"^\|[\s:|-]+\|$", lines[i - 1].strip()):
                continue
            cells = [c.strip() for c in lines[i - 1].strip().strip("|").split("|")]
            rows.append(cells)
        if rows:
            head = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            blocks.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
        continue
    elif re.match(r"^\s*[-•] ", ln):
        items = []
        while i < len(lines) and re.match(r"^\s*[-•] ", lines[i]):
            items.append(f"<li>{inline(re.sub(r'^\s*[-•] ', '', lines[i]))}</li>")
            i += 1
        blocks.append("<ul>" + "".join(items) + "</ul>")
        continue
    elif re.match(r"^\s*\d+\. ", ln):
        items = []
        while i < len(lines) and re.match(r"^\s*\d+\. ", lines[i]):
            items.append(f"<li>{inline(re.sub(r'^\s*\d+\. ', '', lines[i]))}</li>")
            i += 1
        blocks.append("<ol>" + "".join(items) + "</ol>")
        continue
    elif ln.strip():
        para = [ln]
        while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|\||\s*[-•]\s|\s*\d+\.\s|---)", lines[i + 1]):
            i += 1
            para.append(lines[i].rstrip())
        blocks.append(f"<p>{inline(' '.join(para))}</p>")
    i += 1

body = []
for b in blocks:
    if b.startswith("T01<h1>"):
        t, sub = b[7:], ""
        if blocks.index(b) + 1 < len(blocks) and blocks[blocks.index(b) + 1].startswith("<p>"):
            body.append(f'</main><header class="top"><div class="wrap">{t}{sub}</div></header><main>')
        else:
            body.append(f'</main><header class="top"><div class="wrap">{t}{sub}</div></header><main>')
        continue
    # kapsla sektioner i cards
    if b.startswith(("<h2>", "<h3>")):
        if card:
            body.append("</div>")
        body.append('<div class="card">' + b)
        card = True
        continue
    if card and (b.startswith(("<h2>", "<h3>")) or b == "<hr>"):
        body.append("</div>")
        card = False
        if b == "<hr>":
            continue
    body.append(b)
if card:
    body.append("</div>")

out = f"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(re.search(r'^# (.+)$', text, re.M).group(1) if re.search(r'^# (.+)$', text, re.M) else 'Veckorapport')}</title>
<style>{CSS}</style></head>
<body><main data-x="x">{"".join(body)}</main>
</body></html>"""
out = out.replace('<main data-x="x"><header class="top"><div class="wrap">', '<div data-x="x"><header class="top"><div class="wrap">')
out = re.sub(r"</header><main>", "</header><main>", out)
open(DST, "w", encoding="utf-8").write(out)
print(f"skrev {DST} ({len(out)} bytes)")
