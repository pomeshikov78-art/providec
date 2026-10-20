#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Конвертер Markdown → HTML-документ с боковым оглавлением и стабильными якорями.
Якоря: "4.7. Заголовок"→#tz-4-7 · "ЗАДАЧА 13."→#tz-z-13 · "ПРИЛОЖЕНИЕ 4"→#tz-app-4 ·
"ИВП-GEO-2."→#tz-ivp-geo-2 · внутри приложений: "3.7."→#tz-a3-3-7
"""
import re, sys, html as H

def slugify(txt, app=None):
    t = re.sub(r'[*`]', '', txt).strip()
    m = re.match(r'^(\d+(?:\.\d+)*)\.?\s', t)
    if m:
        num = m.group(1).replace('.', '-')
        return ("tz-a%s-%s" % (app, num)) if app else ("tz-" + num)
    m = re.match(r'^ФАЗА\s+(\d+)', t)
    if m: return "ph-" + m.group(1)
    m = re.match(r'^ЗАДАЧА\s+(\d+)', t)
    if m: return "tz-z-" + m.group(1)
    m = re.match(r'^ПРИЛОЖЕНИЕ\s+(\d+)', t)
    if m: return "tz-app-" + m.group(1)
    m = re.match(r'^ИВП-([0-9A-Za-zA-Zа-я-]+?)\.', t)
    if m: return "tz-ivp-" + re.sub(r'[^0-9a-zA-Zа-яА-Я-]', '', m.group(1)).lower()
    return None

def inline(s):
    s = H.escape(s, quote=False)
    codes = []
    def _stash(m):
        codes.append(m.group(1))
        return "\x00%d\x00" % (len(codes) - 1)
    s = re.sub(r'`([^`]+)`', _stash, s)          # защищаем код от последующих замен
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<em>\1</em>', s)
    for i, c in enumerate(codes):
        s = s.replace("\x00%d\x00" % i, '<code>%s</code>' % c)
    return s

def convert(md):
    lines = md.split('\n'); out = []; toc = []; seq = 0; i = 0; n = len(lines); cur_app = None
    while i < n:
        ln = lines[i]; st = ln.strip()
        if st.startswith('```'):
            i += 1; buf = []
            while i < n and not lines[i].strip().startswith('```'):
                buf.append(lines[i]); i += 1
            i += 1
            out.append('<pre class="diagram">' + H.escape('\n'.join(buf)) + '</pre>')
            continue
        m = re.match(r'^(#{1,4})\s+(.*)$', ln)
        if m:
            lvl = len(m.group(1)); txt = m.group(2).strip()
            seq += 1
            ma = re.match(r'^ПРИЛОЖЕНИЕ\s+(\d+)', txt)
            if ma: cur_app = ma.group(1)
            a = slugify(txt, cur_app) or ("s%d" % seq)
            tag = {1: 'h1', 2: 'h2', 3: 'h3', 4: 'h4'}[lvl]
            cls = ' class="doc-h1"' if lvl == 1 else ''
            out.append('<%s id="%s"%s>%s</%s>' % (tag, a, cls, inline(txt), tag))
            if lvl <= 2: toc.append((lvl, a, txt))
            i += 1; continue
        if st.startswith('|') and i+1 < n and re.match(r'^\s*\|[\s:\-|]+\|\s*$', lines[i+1]):
            hdr = [c.strip() for c in st.strip('|').split('|')]
            i += 2; rows = []
            while i < n and lines[i].strip().startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')]); i += 1
            t = '<div class="tw"><table><thead><tr>' + ''.join('<th>%s</th>' % inline(c) for c in hdr) + '</tr></thead><tbody>'
            for r in rows:
                while len(r) < len(hdr): r.append('')
                t += '<tr>' + ''.join('<td>%s</td>' % inline(c) for c in r[:len(hdr)]) + '</tr>'
            out.append(t + '</tbody></table></div>')
            continue
        if st.startswith('- '):
            buf = []
            while i < n and lines[i].strip().startswith('- '):
                buf.append('<li>%s</li>' % inline(lines[i].strip()[2:])); i += 1
            out.append('<ul>' + ''.join(buf) + '</ul>'); continue
        if re.match(r'^\d+\.\s', st):
            buf = []
            while i < n and re.match(r'^\d+\.\s', lines[i].strip()):
                buf.append('<li>%s</li>' % inline(re.sub(r'^\d+\.\s', '', lines[i].strip()))); i += 1
            out.append('<ol>' + ''.join(buf) + '</ol>'); continue
        if st == '---':
            out.append('<hr>'); i += 1; continue
        if st == '':
            i += 1; continue
        out.append('<p>%s</p>' % inline(st)); i += 1
    return '\n'.join(out), toc

TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<style>
:root{--ink:#1a2433;--mut:#5b6b80;--acc:#0f4c81;--acc2:#1267a8;--line:#d7dee8;--bg:#f4f6f9;--card:#fff;--code:#eef2f7}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font:15px/1.68 -apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif}
#side{position:fixed;top:0;left:0;bottom:0;width:312px;background:#101c2e;color:#c7d3e4;overflow-y:auto;padding:18px 12px 40px;z-index:20}
#side .sh{padding:6px 10px 14px;border-bottom:1px solid #22354e;margin-bottom:10px}
#side .sh b{color:#fff;font-size:15px;display:block;letter-spacing:.3px}
#side .sh span{font-size:11px;color:#7e93ad;letter-spacing:1.4px;text-transform:uppercase}
#side a{display:block;color:#a9bacd;text-decoration:none;font-size:12.4px;padding:4.5px 10px;border-radius:6px;border-left:2px solid transparent;line-height:1.4}
#side a:hover{background:#182940;color:#fff}
#side a.t1{color:#e8eef6;font-weight:700;margin-top:12px;font-size:12.8px;border-left-color:#2f6ea8}
#side a.t2{padding-left:22px}
#side .prog{margin:10px 6px 4px;display:block;background:#1b5e94;color:#fff;text-align:center;border-radius:8px;padding:8px;font-size:12px;text-decoration:none}
#side .prog:hover{background:#2272b0}
#main{margin-left:312px;padding:34px 46px 90px;max-width:1080px}
.doc{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:44px 52px 54px;box-shadow:0 8px 34px rgba(16,28,46,.07)}
h1.doc-h1{font-size:22px;color:var(--acc);text-align:center;margin:44px 0 20px;padding:26px 0 20px;border-top:3px double var(--acc);letter-spacing:.5px;text-transform:uppercase}
h1.doc-h1:first-child{margin-top:0;border-top:none}
h2{font-size:18px;color:#123;margin:30px 0 12px;padding-bottom:7px;border-bottom:2px solid var(--line)}
h3{font-size:15.5px;color:var(--acc2);margin:22px 0 9px}
h4{font-size:14px;color:#2c3e55;margin:16px 0 7px}
p{margin:8px 0;text-align:justify}
ul,ol{margin:8px 0 12px 26px}
li{margin:3px 0}
strong{color:#0d2b4a}
code{background:var(--code);border:1px solid var(--line);border-radius:4px;padding:1px 5px;font:12.5px/1.5 Consolas,'SF Mono',monospace;color:#0f4c81}
pre.diagram{background:#0d1a2b;color:#bfe3ff;border-radius:10px;padding:16px 18px;overflow-x:auto;font:11.5px/1.42 Consolas,'SF Mono','Cascadia Code',monospace;margin:14px 0;white-space:pre}
hr{border:none;border-top:1px dashed var(--line);margin:26px 0}
.tw{overflow-x:auto;margin:12px 0}
table{width:100%;border-collapse:collapse;font-size:13.2px}
th{background:#eef3f9;color:#22384f;text-align:left;padding:8px 10px;border:1px solid var(--line);font-size:12.4px}
td{padding:7px 10px;border:1px solid var(--line);vertical-align:top}
tr:nth-child(even) td{background:#fafcfe}
.cover{text-align:center;padding:20px 0 6px}
.stamp{display:inline-block;border:2px solid var(--acc);color:var(--acc);border-radius:8px;padding:6px 18px;font-size:12px;letter-spacing:2px;text-transform:uppercase;margin-bottom:16px}
#topbtn{position:fixed;right:26px;bottom:26px;background:var(--acc);color:#fff;border:none;border-radius:10px;padding:11px 16px;font-size:13px;cursor:pointer;box-shadow:0 8px 24px rgba(15,76,129,.35);z-index:30}
#pbtn{position:fixed;right:26px;bottom:76px;background:#fff;color:var(--acc);border:1px solid var(--acc);border-radius:10px;padding:10px 16px;font-size:13px;cursor:pointer;z-index:30}
@media(max-width:980px){#side{display:none}#main{margin-left:0;padding:16px}.doc{padding:22px 18px}}
@media print{
 #side,#topbtn,#pbtn{display:none}
 #main{margin:0;padding:0;max-width:none}
 body{background:#fff}
 .doc{border:none;box-shadow:none;padding:0;border-radius:0}
 h1.doc-h1{page-break-before:always}
 h1.doc-h1:first-child{page-break-before:avoid}
 table,pre.diagram{page-break-inside:avoid}
}
</style>
</head>
<body>
<nav id="side">
 <div class="sh"><b>__SIDE_TITLE__</b><span>__SIDE_SUB__</span></div>
 <a class="t1" href="#top">▸ Начало документа</a>
__TOC__
__BACK__
</nav>
<div id="main">
<div class="doc" id="top">
<div class="cover">
<div class="stamp">__STAMP__</div>
<div style="font-size:12px;color:var(--mut);letter-spacing:1.4px;text-transform:uppercase">__COVER_SUB__</div>
</div>
__BODY__
</div>
</div>
<button id="pbtn" onclick="window.print()">🖨 Печать / PDF</button>
<button id="topbtn" onclick="window.scrollTo({top:0,behavior:'smooth'})">↑ Наверх</button>
</body>
</html>'''

def build(md, title, side_title, side_sub, stamp, cover_sub, back=None):
    body, toc = convert(md)
    toc_html = []
    for lvl, a, txt in toc:
        clean = re.sub(r'[*`]', '', txt)
        cls = 't1' if lvl == 1 else 't2'
        toc_html.append('<a class="%s" href="#%s">%s</a>' % (cls, a, H.escape(clean)))
    back_html = ('<a class="prog" href="%s">⚡ %s</a>' % back) if back else ''
    page = (TEMPLATE.replace('__TITLE__', H.escape(title))
            .replace('__SIDE_TITLE__', side_title).replace('__SIDE_SUB__', side_sub)
            .replace('__STAMP__', stamp).replace('__COVER_SUB__', cover_sub)
            .replace('__TOC__', '\n'.join(toc_html)).replace('__BACK__', back_html)
            .replace('__BODY__', body))
    return page, len(toc)
