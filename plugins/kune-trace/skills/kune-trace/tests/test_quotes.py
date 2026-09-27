"""Rules 2 and 3: every line cites an existing source, and quotes are verbatim."""

import unittest

from support import LedgerTestCase


class CiteTest(LedgerTestCase):

    def setUp(self):
        super().setUp()
        self.seed()

    def test_line_without_a_cite_is_refused(self):
        before = len(self.events())
        r = self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "黄色い鼻水", ok=False)
        self.assertEqual(r.code, 2)
        self.assertIn("cite", r.err)
        self.assertEqual(len(self.events()), before)

    def test_cite_to_a_missing_source_is_refused(self):
        r = self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "黄色い鼻水",
                     "--cite", "S0099", ok=False)
        self.assertIn("S0099", r.err)

    def test_malformed_cite_is_refused(self):
        r = self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "黄色い鼻水",
                     "--cite", "S0001：黄色い鼻水", ok=False)  # full-width colon
        self.assertIn("S0001", r.err)

    def test_crafted_line_without_cites_fails_check(self):
        self.craft("add_line", {"id": "L0001", "doc": "D0001", "text": "黄色い鼻水", "type": "self", "cites": []})
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertIn((2, "L0001"), self.rules(data["errors"]))

    def test_crafted_cite_to_missing_source_fails_check(self):
        self.craft("add_line", {"id": "L0001", "doc": "D0001", "text": "黄色い鼻水", "type": "self",
                                "cites": [{"source": "S0042"}]})
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertIn((2, "L0001"), self.rules(data["errors"]))


class QuoteTest(LedgerTestCase):

    def setUp(self):
        super().setUp()
        self.seed()

    def test_verbatim_substring_is_accepted(self):
        self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "黄色い鼻水（2026-09-16）",
                 "--cite", "S0001:黄色い鼻水が出る")
        code, data = self.check()
        self.assertEqual(code, 0, data)
        self.assertEqual(self.events()[-1]["data"]["cites"], [{"source": "S0001", "quote": "黄色い鼻水が出る"}])

    def test_quote_may_contain_a_colon(self):
        self.cli("add-source", "--kind", "photo", "--text", "用法：1回1錠")  # S0005
        self.cli("add-line", "--doc", "D0001", "--type", "document", "--text", "用法：1回1錠",
                 "--cite", "S0005:用法：1回1錠")
        self.assertEqual(self.events()[-1]["data"]["cites"][0]["quote"], "用法：1回1錠")

    def test_whitespace_is_normalized_only(self):
        # the source has a full-width space; the quote uses an ASCII space
        self.cli("add-line", "--doc", "D0001", "--type", "document",
                 "--text", "カルボシステイン錠500mg「JG」：1回1錠",
                 "--cite", "S0002:カルボシステイン錠500mg「JG」 1回1錠")
        code, data = self.check()
        self.assertEqual(code, 0, data)

    def test_newlines_count_as_whitespace(self):
        self.cli("add-source", "--kind", "document", "--stdin", stdin_bytes="1回1錠\n1日3回\n".encode("utf-8"))
        self.cli("add-line", "--doc", "D0001", "--type", "document", "--text", "1回1錠、1日3回",
                 "--cite", "S0005:1回1錠 1日3回")
        code, data = self.check()
        self.assertEqual(code, 0, data)

    def test_non_verbatim_quote_is_refused(self):
        before = len(self.events())
        # the escalation the whole skill exists to catch: 少し -> かなり
        self.cli("add-source", "--kind", "voice", "--text", "鼻づまりは少し良くなった気がする")  # S0005
        r = self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "鼻づまり：かなり改善",
                     "--cite", "S0005:かなり良くなった", ok=False)
        self.assertEqual(r.code, 2)
        self.assertIn("verbatim", r.err)
        self.assertEqual(len(self.events()), before + 1)

    def test_missing_space_is_not_whitespace_normalization(self):
        r = self.cli("add-line", "--doc", "D0001", "--type", "document", "--text", "カルボシステイン",
                     "--cite", "S0002:1回1錠1日3回", ok=False)
        self.assertIn("verbatim", r.err)

    def test_empty_quote_is_refused(self):
        r = self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "黄色い鼻水",
                     "--cite", "S0001:   ", ok=False)
        self.assertIn("quote", r.err)

    def test_crafted_non_verbatim_quote_fails_check(self):
        self.craft("add_line", {"id": "L0001", "doc": "D0001", "text": "鼻づまり：かなり改善", "type": "self",
                                "cites": [{"source": "S0001", "quote": "かなり良くなった"}]})
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertIn((3, "L0001"), self.rules(data["errors"]))

    def test_revision_with_a_bad_quote_is_refused(self):
        self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "黄色い鼻水（2026-09-16）",
                 "--cite", "S0001:黄色い鼻水が出る")
        r = self.cli("revise-line", "--line", "L0001", "--cite", "S0001:緑の鼻水", "--reason", "引用を変更", ok=False)
        self.assertIn("verbatim", r.err)


if __name__ == "__main__":
    unittest.main()
