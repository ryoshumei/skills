"""HTML for ``ledger.py render``: one static, self-contained page.

Pure function of the view model that ledger.py builds (no clock, no file
access here). Inline CSS and JS only; a Content-Security-Policy forbids every
network load, so the page never fetches anything. Source texts reach the page
only as JSON inside a script block and are put into the dialog with
textContent, never as HTML.
"""

from __future__ import annotations

import html
import json

CSS = """
:root {
  color-scheme: light dark;
  --bg: #f6f5f1; --card: #ffffff; --fg: #1f1e1c; --muted: #5d5b55; --line: #dcd8ce;
  --chip-bg: #f1efe9; --chip-border: #c9c4b8; --chip-hover: #e7e3d8; --focus: #1d4f7a;
  --mark-bg: #ffe98a; --mark-fg: #1f1e1c;
  --quoted: #1d4f7a; --quoted-bg: #e5eef7;
  --document: #235d34; --document-bg: #e3f0e7;
  --self: #5a3f84; --self-bg: #eee8f6;
  --guess: #7a4d00; --guess-bg: #fbf0da; --guess-border: #a86b00;
  --ok: #1f6b3a; --ok-bg: #e3f1e7; --bad: #a4271b; --bad-bg: #f9e6e3; --warn: #7a4d00; --warn-bg: #fbf0da;
  --none-bg: #eceae4;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #151513; --card: #1f1e1c; --fg: #ecebe6; --muted: #a9a69d; --line: #3a3833;
    --chip-bg: #2a2926; --chip-border: #54514a; --chip-hover: #34322e; --focus: #8cc0ee;
    --mark-bg: #6b5600; --mark-fg: #fff8d6;
    --quoted: #9cc7ef; --quoted-bg: #1b2a38;
    --document: #9fd8ae; --document-bg: #1b2d21;
    --self: #cdb8ef; --self-bg: #2a2237;
    --guess: #f1c56b; --guess-bg: #33280f; --guess-border: #d69e2e;
    --ok: #9fd8ae; --ok-bg: #1b2d21; --bad: #f2a497; --bad-bg: #3a1d19; --warn: #f1c56b; --warn-bg: #33280f;
    --none-bg: #2a2926;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font-family: system-ui, -apple-system, "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Noto Sans JP",
    "Yu Gothic UI", "Meiryo", sans-serif;
  font-size: 16px; line-height: 1.6;
}
.kt-wrap { max-width: 720px; margin: 0 auto; padding: 0 16px; }
.kt-top { background: var(--card); border-bottom: 1px solid var(--line); padding: 16px 0 12px; }
.kt-tags { margin: 0 0 8px; display: flex; flex-wrap: wrap; gap: 8px; }
.kt-tag { display: inline-block; font-size: 13px; font-weight: 700; padding: 2px 10px; border-radius: 999px;
  background: var(--warn-bg); color: var(--warn); border: 1px solid currentColor; }
h1 { font-size: 21px; line-height: 1.4; margin: 0 0 4px; overflow-wrap: anywhere; }
.kt-sub { margin: 0 0 8px; color: var(--muted); font-size: 14px; overflow-wrap: anywhere; }
.kt-check { margin: 0 0 6px; padding: 8px 12px; border-radius: 10px; font-size: 14px; overflow-wrap: anywhere; }
.kt-check strong { font-weight: 700; }
.kt-check-pass { background: var(--ok-bg); color: var(--ok); }
.kt-check-fail { background: var(--bad-bg); color: var(--bad); }
.kt-check-none { background: var(--none-bg); color: var(--muted); }
.kt-check-stale { display: block; color: var(--warn); font-weight: 700; }
.kt-meta { margin: 0; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
main { padding-top: 16px; padding-bottom: 24px; }
.kt-legend { margin: 0 0 4px; font-size: 14px; }
.kt-legend summary { min-height: 44px; padding: 10px 4px; cursor: pointer; color: var(--focus); }
.kt-legend summary:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }
.kt-legend ul { list-style: none; margin: 0 0 8px; padding: 0; display: grid;
  grid-template-columns: max-content minmax(0, 1fr); gap: 8px 10px; align-items: baseline; font-size: 13px; color: var(--muted); }
.kt-legend li { display: contents; }
.kt-legend li span:last-child { overflow-wrap: anywhere; }
.kt-hint { margin: 0 0 16px; font-size: 13px; color: var(--muted); }
.kt-d-label { margin: 0 0 4px; font-size: 13px; color: var(--muted); }
.kt-nav { margin: 0 0 16px; padding-left: 20px; }
.kt-nav a { color: var(--focus); }
.kt-doc { margin: 0 0 24px; }
.kt-doc h2 { font-size: 18px; margin: 0 0 2px; overflow-wrap: anywhere; }
.kt-doc-meta { margin: 0 0 12px; color: var(--muted); font-size: 14px; overflow-wrap: anywhere; }
.kt-lines { list-style: none; margin: 0; padding: 0; }
.kt-line { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 12px; margin: 0 0 12px; }
.kt-line.t-guess { border: 2px dashed var(--guess-border); background: var(--guess-bg); }
.kt-line-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 0 0 6px; }
.kt-badge { display: inline-block; font-size: 13px; font-weight: 700; line-height: 1.5; padding: 1px 10px;
  border-radius: 999px; border: 1px solid currentColor; }
.kt-badge.t-quoted { color: var(--quoted); background: var(--quoted-bg); }
.kt-badge.t-document { color: var(--document); background: var(--document-bg); }
.kt-badge.t-self { color: var(--self); background: var(--self-bg); }
.kt-badge.t-guess { color: var(--guess); background: var(--guess-bg); border-style: dashed; border-width: 2px; }
.kt-status { font-size: 13px; color: var(--muted); }
.kt-status.is-approved { color: var(--ok); font-weight: 700; }
.kt-lid { font-size: 12px; color: var(--muted); margin-left: auto; }
.kt-text { margin: 0 0 8px; font-size: 16px; overflow-wrap: anywhere; }
.kt-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  display: inline-flex; align-items: center; min-height: 44px; min-width: 44px; max-width: 100%;
  padding: 6px 14px; border-radius: 22px; border: 1px solid var(--chip-border); background: var(--chip-bg);
  color: var(--fg); font: inherit; font-size: 14px; line-height: 1.3; text-align: left; cursor: pointer;
  overflow-wrap: anywhere;
}
.chip:hover { background: var(--chip-hover); }
.chip:focus-visible, .kt-close:focus-visible, .kt-nav a:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }
.kt-foot { color: var(--muted); font-size: 13px; padding-bottom: 32px; }
dialog {
  width: min(640px, calc(100vw - 24px)); max-height: calc(100vh - 24px); padding: 0;
  border: 1px solid var(--line); border-radius: 16px; background: var(--card); color: var(--fg);
}
dialog::backdrop { background: rgba(0, 0, 0, 0.45); }
.kt-d-inner { display: flex; flex-direction: column; max-height: calc(100vh - 26px); }
.kt-d-head { display: flex; align-items: center; gap: 8px; padding: 8px 8px 8px 16px; border-bottom: 1px solid var(--line); }
.kt-d-head h2 { font-size: 16px; margin: 0; flex: 1; overflow-wrap: anywhere; }
.kt-close { min-height: 44px; min-width: 44px; padding: 0 14px; border-radius: 22px; border: 1px solid var(--chip-border);
  background: var(--chip-bg); color: var(--fg); font: inherit; font-size: 14px; cursor: pointer; }
.kt-d-body { overflow-y: auto; padding: 12px 16px 16px; }
.kt-d-line { margin: 0 0 10px; font-size: 14px; color: var(--muted); overflow-wrap: anywhere; }
.kt-verbatim { margin: 0 0 10px; padding: 10px 12px; border-left: 4px solid var(--chip-border); background: var(--bg);
  white-space: pre-wrap; overflow-wrap: anywhere; font-size: 16px; }
.kt-verbatim mark { background: var(--mark-bg); color: var(--mark-fg); padding: 0 1px; }
.kt-d-quote { margin: 0 0 10px; font-size: 14px; overflow-wrap: anywhere; }
.kt-d-meta { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 4px 12px; margin: 0 0 12px; font-size: 14px; }
.kt-d-meta dt { color: var(--muted); }
.kt-d-meta dd { margin: 0; overflow-wrap: anywhere; }
.kt-d-body h3 { font-size: 15px; margin: 12px 0 6px; }
.kt-hist { margin: 0; padding-left: 20px; font-size: 14px; }
.kt-hist li { margin: 0 0 6px; overflow-wrap: anywhere; }
.kt-hist-at { display: block; color: var(--muted); font-size: 13px; }
@media print {
  .kt-top { border-bottom: 1px solid #999; }
  .chip { border-color: #999; }
  dialog { display: none; }
}
"""

JS = """
(function () {
  'use strict';
  var L = /*LABELS*/;
  var data = JSON.parse(document.getElementById('kt-data').textContent);
  var dlg = document.getElementById('kt-dialog');
  var body = document.getElementById('kt-d-body');
  var title = document.getElementById('kt-d-title');
  var opener = null;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined && text !== null) { e.textContent = text; }
    return e;
  }
  function row(dl, label, value) {
    if (value === undefined || value === null || value === '') { return; }
    dl.appendChild(el('dt', null, label));
    dl.appendChild(el('dd', null, String(value)));
  }
  function verbatim(text, spans) {
    var q = el('blockquote', 'kt-verbatim');
    var pos = 0;
    spans.slice().sort(function (a, b) { return a[0] - b[0]; }).forEach(function (s) {
      if (s[0] < pos) { return; }
      q.appendChild(document.createTextNode(text.slice(pos, s[0])));
      q.appendChild(el('mark', null, text.slice(s[0], s[1])));
      pos = s[1];
    });
    q.appendChild(document.createTextNode(text.slice(pos)));
    return q;
  }
  function open(chip) {
    var src = data.sources[chip.getAttribute('data-source')];
    var line = data.lines[chip.getAttribute('data-line')];
    if (!src || !line) { return; }
    var cite = line.cites[src.id] || { quotes: [], spans: [] };
    title.textContent = L.source + ' ' + src.id + L.sep + src.chip;
    body.textContent = '';
    body.appendChild(el('p', 'kt-d-line', L.line + L.open + line.id + L.sep + line.type_label + L.close + line.text));
    body.appendChild(el('p', 'kt-d-label', L.verbatim));
    body.appendChild(verbatim(src.text, cite.spans));
    if (cite.quotes.length) {
      body.appendChild(el('p', 'kt-d-quote', L.quoted + cite.quotes.map(function (q) { return L.qopen + q + L.qclose; }).join('')));
    }
    var dl = el('dl', 'kt-d-meta');
    row(dl, L.kind, src.kind_label);
    row(dl, L.speaker, src.speaker);
    row(dl, L.captured, src.captured);
    row(dl, L.happened, src.happened);
    row(dl, L.file, src.file);
    row(dl, L.page, src.page);
    row(dl, L.media, src.media_time);
    body.appendChild(dl);
    body.appendChild(el('h3', null, L.history));
    var ol = el('ol', 'kt-hist');
    line.history.forEach(function (h) {
      var li = el('li');
      li.appendChild(el('span', 'kt-hist-at', h.at + ' ' + h.actor));
      li.appendChild(el('span', 'kt-hist-what', h.what));
      ol.appendChild(li);
    });
    body.appendChild(ol);
    opener = chip;
    if (typeof dlg.showModal === 'function') { dlg.showModal(); } else { dlg.setAttribute('open', ''); }
    body.scrollTop = 0;
  }
  function close() {
    if (typeof dlg.close === 'function') { dlg.close(); return; }
    dlg.removeAttribute('open');
    if (opener) { opener.focus(); }
  }
  document.addEventListener('click', function (e) {
    var t = e.target;
    var chip = t && t.closest ? t.closest('button.chip') : null;
    if (chip) { open(chip); }
  });
  document.getElementById('kt-close').addEventListener('click', close);
  dlg.addEventListener('click', function (e) { if (e.target === dlg) { close(); } });
  dlg.addEventListener('close', function () { if (opener) { opener.focus(); } });
})();
"""

# Dialog labels, kept apart from the logic so a later profile can relabel them.
LABELS = {
    "source": "出典",
    "line": "この行",
    "sep": "・",
    "open": "（",
    "close": "）：",
    "qopen": "「",
    "qclose": "」",
    "verbatim": "元の記録（原文のまま）",
    "quoted": "この行が引用した部分：",
    "kind": "種類",
    "speaker": "発言者",
    "captured": "記録した時刻",
    "happened": "出来事の日時",
    "file": "ファイル",
    "page": "ページ",
    "media": "再生位置",
    "history": "この行の履歴",
}

CSP = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'none'; "
       "base-uri 'none'; form-action 'none'")


def esc(text):
    return html.escape("" if text is None else str(text), quote=True)


def script_json(obj):
    """JSON that is safe inside <script>: no '<', '>' or '&' characters survive."""
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def render_check(check):
    cls = {"pass": "kt-check-pass", "fail": "kt-check-fail"}.get(check["state"], "kt-check-none")
    parts = ['<p class="kt-check %s" role="status"><strong>%s</strong>' % (cls, esc(check["label"]))]
    if check.get("detail"):
        parts.append("<span>%s</span>" % esc(check["detail"]))
    if check.get("stale"):
        parts.append('<span class="kt-check-stale">%s</span>' % esc(check["stale"]))
    parts.append("</p>")
    return "".join(parts)


def render_line(line):
    chips = "".join(
        '<button type="button" class="chip" data-line="%s" data-source="%s" aria-haspopup="dialog" '
        'aria-label="%s">%s</button>' % (esc(line["id"]), esc(c["source"]), esc("出典を見る：" + c["label"]), esc(c["label"]))
        for c in line["chips"])
    status_cls = "is-approved" if line["status"] == "approved" else "is-draft"
    return (
        '<li class="kt-line t-%(type)s %(status_cls)s" id="%(id)s">'
        '<div class="kt-line-head"><span class="kt-badge t-%(type)s">%(type_label)s</span>'
        '<span class="kt-status %(status_cls)s">%(status_label)s</span><span class="kt-lid">%(id)s</span></div>'
        '<p class="kt-text">%(text)s</p>'
        '<div class="kt-chips">%(chips)s</div></li>'
    ) % {"type": esc(line["type"]), "status_cls": status_cls, "id": esc(line["id"]),
         "type_label": esc(line["type_label"]), "status_label": esc(line["status_label"]),
         "text": esc(line["text"]), "chips": chips}


def render_doc(doc, heading=True):
    """One doc. A page with a single doc shows its title in the page header instead."""
    lines = "".join(render_line(l) for l in doc["lines"]) or '<li class="kt-line">（まだ行がありません）</li>'
    if not heading:
        return ('<section class="kt-doc" id="%s" aria-labelledby="kt-title"><ol class="kt-lines">%s</ol></section>'
                % (esc(doc["id"]), lines))
    meta = esc(doc["kind_label"])
    if doc.get("for"):
        meta += "・宛先：" + esc(doc["for"])
    return ('<section class="kt-doc" id="%(id)s" aria-labelledby="%(id)s-h"><h2 id="%(id)s-h">%(title)s</h2>'
            '<p class="kt-doc-meta">%(meta)s</p><ol class="kt-lines">%(lines)s</ol></section>'
            ) % {"id": esc(doc["id"]), "title": esc(doc["title"]), "meta": meta, "lines": lines}


def render_page(model):
    tags = ""
    if model["sample"]:
        tags = '<p class="kt-tags"><span class="kt-tag">サンプルデータ</span></p>'
    broken = ""
    if model.get("chain_broken"):
        broken = '<p class="kt-check kt-check-fail"><strong>記録の連鎖が壊れています。チェックを実行してください。</strong></p>'
    legend = "".join('<li><span class="kt-badge t-%s">%s</span><span>%s</span></li>'
                     % (esc(l["type"]), esc(l["label"]), esc(l["help"])) for l in model["legend"])
    nav = ""
    if len(model["docs"]) > 1:
        nav = '<ol class="kt-nav">%s</ol>' % "".join(
            '<li><a href="#%s">%s</a></li>' % (esc(d["id"]), esc(d["title"])) for d in model["docs"])
    single = len(model["docs"]) == 1
    docs = "".join(render_doc(d, heading=not single) for d in model["docs"]) or '<p>まだ文書がありません。</p>'
    sub = ""
    if single:
        d = model["docs"][0]
        sub = esc(d["kind_label"]) + ("・宛先：" + esc(d["for"]) if d.get("for") else "")
    js = JS.replace("/*LABELS*/", script_json(LABELS), 1)
    return """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta http-equiv="Content-Security-Policy" content="%(csp)s">
<meta name="referrer" content="no-referrer">
<title>%(title)s</title>
<style>%(css)s</style>
</head>
<body>
<header class="kt-top"><div class="kt-wrap">%(tags)s<h1 id="kt-title">%(title)s</h1>%(sub)s%(broken)s%(check)s
<p class="kt-meta">表示の作成：%(generated)s・時刻は %(tz)s</p></div></header>
<main class="kt-wrap">
<details class="kt-legend"><summary>種類の見かた</summary><ul>%(legend)s</ul></details>
<p class="kt-hint">出典のボタンを押すと、元の記録を原文のまま表示します。</p>
<noscript><p class="kt-hint">出典の表示には JavaScript が必要です。</p></noscript>
%(nav)s%(docs)s
</main>
<footer class="kt-wrap kt-foot">記録を整理して表示するだけのページです。医学的な判断や助言は含みません。</footer>
<dialog id="kt-dialog" aria-labelledby="kt-d-title"><div class="kt-d-inner">
<div class="kt-d-head"><h2 id="kt-d-title">出典</h2><button type="button" class="kt-close" id="kt-close" autofocus>閉じる</button></div>
<div class="kt-d-body" id="kt-d-body"></div>
</div></dialog>
<script type="application/json" id="kt-data">%(data)s</script>
<script>%(js)s</script>
</body>
</html>
""" % {
        "csp": esc(CSP), "title": esc(model["title"]), "css": CSS, "tags": tags,
        "sub": ('<p class="kt-sub">%s</p>' % sub) if sub else "", "broken": broken,
        "check": render_check(model["check"]), "generated": esc(model["generated"]), "tz": esc(model["tz_label"]),
        "legend": legend, "nav": nav, "docs": docs, "data": script_json(model["data"]), "js": js,
    }
