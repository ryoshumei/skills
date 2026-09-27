"""``render``: one static, self-contained HTML file; no resource loads from the network."""

import json
import re
import unittest

from support import LedgerTestCase

RESOURCE_LOAD = [
    re.compile(r"""\b(?:src|href|srcset|poster|data|action|formaction)\s*=\s*["']?\s*(?:https?:)?//""", re.I),
    re.compile(r"""url\(\s*["']?\s*(?:https?:)?//""", re.I),
    re.compile(r"@import", re.I),
    re.compile(r"<link\b", re.I),
    re.compile(r"<script\b[^>]*\bsrc\s*=", re.I),
    re.compile(r"<(?:img|iframe|embed|object|video|audio|source)\b", re.I),
]


class RenderTest(LedgerTestCase):

    def setUp(self):
        super().setUp()
        self.seed()
        self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "黄色い鼻水：2026-09-16から",
                 "--cite", "S0001:黄色い鼻水が出る")
        self.cli("add-line", "--doc", "D0001", "--type", "document",
                 "--text", "カルボシステイン錠500mg「JG」：1回1錠 1日3回 毎食後",
                 "--cite", "S0002:カルボシステイン錠500mg「JG」　1回1錠　1日3回　毎食後")
        self.cli("add-line", "--doc", "D0001", "--type", "quoted", "--text", "「副鼻腔炎かもしれない」（2026-09-18）",
                 "--cite", "S0003:副鼻腔炎かもしれない")
        self.cli("add-line", "--doc", "D0001", "--type", "guess", "--text", "ChatGPTの推測：「副鼻腔炎かも」",
                 "--cite", "S0004:副鼻腔炎かも")
        self.cli("approve", "--line", "L0001")

    def render(self, *argv):
        r = self.cli("render", *argv)
        path = r.out.strip().splitlines()[-1].split()[-1]
        return r, path

    def html(self, name="index.html"):
        return (self.dir / "views" / name).read_text(encoding="utf-8")

    def test_render_writes_an_index(self):
        r, path = self.render()
        self.assertTrue(path.endswith("index.html"), r.out)
        html = self.html()
        self.assertTrue(html.lower().startswith("<!doctype html>"))
        self.assertIn('lang="ja"', html)
        self.assertIn('name="viewport"', html)
        self.assertIn("prefers-color-scheme: dark", html)

    def test_no_http_or_https_anywhere(self):
        self.render()
        html = self.html()
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        for rx in RESOURCE_LOAD:
            self.assertIsNone(rx.search(html), rx.pattern)

    def test_urls_in_her_sources_are_text_not_loads(self):
        self.cli("add-source", "--kind", "chat",
                 "--text", 'https://example.com/a.png を見た</script><script>alert(1)</script><img src=x>')
        self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "リンクを共有（2026-09-24）",
                 "--cite", "S0005")
        self.render()
        html = self.html()
        for rx in RESOURCE_LOAD:
            self.assertIsNone(rx.search(html), rx.pattern)
        self.assertNotIn("</script><script>alert", html)
        self.assertEqual(html.count("</script>"), 2, "only the page's own two script blocks")

    def test_each_line_shows_type_status_and_chips(self):
        self.render()
        html = self.html()
        for label in ("医師の言葉", "書類", "本人", "推測（未確認）", "下書き", "承認済み"):
            self.assertIn(label, html)
        self.assertRegex(html, r'class="[^"]*\bt-guess\b')
        self.assertIn("dashed", html)
        self.assertIn("9/18 写真 p.1", html)
        self.assertIn("9/24 音声 0:03", html)
        self.assertIn("9/24 AIの回答", html)

    def test_chips_are_buttons_with_accessible_names(self):
        self.render()
        html = self.html()
        chips = re.findall(r"<button[^>]*class=\"chip\"[^>]*>", html)
        self.assertEqual(len(chips), 4)
        for chip in chips:
            self.assertIn('type="button"', chip)
            self.assertIn("aria-label=", chip)
            self.assertIn('data-line="L', chip)
            self.assertIn('data-source="S', chip)
        self.assertIn("<dialog", html)
        self.assertIn("min-height: 44px", html)

    def test_dialog_data_has_verbatim_text_and_history(self):
        self.render()
        html = self.html()
        m = re.search(r'<script type="application/json" id="kt-data">(.*?)</script>', html, re.S)
        data = json.loads(m.group(1))
        s = data["sources"]["S0002"]
        self.assertEqual(s["text"], "カルボシステイン錠500mg「JG」　1回1錠　1日3回　毎食後")
        self.assertEqual(s["page"], 1)
        self.assertEqual(s["file"], "photos/yakujo.jpg")
        self.assertIn("2026-09-18", s["happened"])
        self.assertIn("確認済み", s["happened"])
        self.assertIn("未設定", data["sources"]["S0001"]["happened"])
        self.assertIn("2026-09-24 21:00", s["captured"])
        line = data["lines"]["L0001"]
        self.assertEqual([h["op"] for h in line["history"]], ["add_line", "approve"])
        span = line["cites"]["S0001"]["spans"][0]
        self.assertEqual(data["sources"]["S0001"]["text"][span[0]:span[1]], "黄色い鼻水が出る")
        # whitespace-normalized quote maps back onto the verbatim text
        span2 = data["lines"]["L0002"]["cites"]["S0002"]["spans"][0]
        self.assertEqual(data["sources"]["S0002"]["text"][span2[0]:span2[1]],
                         "カルボシステイン錠500mg「JG」　1回1錠　1日3回　毎食後")

    def test_header_shows_check_state(self):
        self.render()
        self.assertIn("チェック未実行", self.html())
        self.check(at="2026-09-24T21:10:00+09:00")
        self.render()
        html = self.html()
        self.assertIn("チェック：合格", html)
        self.assertIn("2026-09-24 21:10", html)
        self.assertNotIn("チェック未実行", html)
        self.cli("add-source", "--kind", "chat", "--text", "朝だけ右の頬が痛い")
        self.render()
        self.assertIn("変更", self.html())  # the check is stale now

    def test_failed_check_is_shown(self):
        self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "右の頬の痛み：昨日から",
                 "--cite", "S0001:頬のあたりが重い")
        self.check()
        self.render()
        self.assertIn("チェック：不合格", self.html())

    def test_a_crafted_relative_happened_at_does_not_break_the_view(self):
        self.craft("add_source", {"id": "S0005", "kind": "chat", "text": "頬が痛い", "happened_at": "昨日",
                                  "happened_confirmed": True})
        self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "頬の痛み（2026-09-23）", "--cite", "S0005")
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertIn((5, "S0005"), self.rules(data["errors"]))
        self.render()
        self.assertIn("形式が正しくありません", self.html())

    def test_broken_chain_is_shown(self):
        log = self.dir / "log.jsonl"
        log.write_bytes(log.read_bytes().replace("黄色い".encode("utf-8"), "白色い".encode("utf-8"), 1))
        self.render()
        self.assertIn("記録の連鎖が壊れています", self.html())

    def test_sample_tag_only_for_sample_ledgers(self):
        self.render()
        self.assertNotIn("サンプルデータ", self.html())

    def test_render_one_doc_and_custom_out(self):
        r, path = self.render("--doc", "D0001")
        self.assertTrue(path.endswith("D0001.html"), r.out)
        self.assertIn("受診メモ（2026-09-25）", self.html("D0001.html"))
        out = self.tmp / "memo.html"
        r, path = self.render("--doc", "D0001", "--out", out)
        self.assertTrue(out.exists())

    def test_render_is_deterministic_for_a_fixed_clock(self):
        self.render()
        a = self.html()
        self.render()
        self.assertEqual(a, self.html())


class SampleTagTest(LedgerTestCase):
    sample = True

    def test_sample_ledger_shows_the_tag(self):
        self.cli("add-source", "--kind", "chat", "--text", "黄色い鼻水が出る")
        self.cli("add-doc", "--kind", "record", "--title", "鼻の記録")
        self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "黄色い鼻水", "--cite", "S0001")
        self.cli("render")
        html = (self.dir / "views" / "index.html").read_text(encoding="utf-8")
        self.assertIn("サンプルデータ", html)


if __name__ == "__main__":
    unittest.main()
