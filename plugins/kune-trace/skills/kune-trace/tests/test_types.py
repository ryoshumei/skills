"""Rule 4: claim types, promotion, and AI answers that can't become facts on their own."""

import unittest

from support import LedgerTestCase


class TypeRuleTest(LedgerTestCase):

    def setUp(self):
        super().setUp()
        self.seed()  # S0001 chat, S0002 photo, S0003 voice, S0004 other_ai, D0001

    def test_unknown_type_is_refused(self):
        r = self.cli("add-line", "--doc", "D0001", "--type", "fact", "--text", "黄色い鼻水",
                     "--cite", "S0001", ok=False)
        self.assertEqual(r.code, 2)

    def test_quoted_needs_a_quote(self):
        r = self.cli("add-line", "--doc", "D0001", "--type", "quoted", "--text", "副鼻腔炎かもしれない",
                     "--cite", "S0003", ok=False)
        self.assertIn("quoted", r.err)
        self.cli("add-line", "--doc", "D0001", "--type", "quoted", "--text", "「副鼻腔炎かもしれない」（2026-09-18）",
                 "--cite", "S0003:副鼻腔炎かもしれない")
        code, data = self.check()
        self.assertEqual(code, 0, data)

    def test_document_needs_a_photo_or_document_source(self):
        r = self.cli("add-line", "--doc", "D0001", "--type", "document", "--text", "黄色い鼻水",
                     "--cite", "S0001:黄色い鼻水", ok=False)
        self.assertIn("photo", r.err)
        self.cli("add-line", "--doc", "D0001", "--type", "document", "--text", "カルボシステイン錠500mg「JG」",
                 "--cite", "S0002:カルボシステイン錠500mg「JG」")

    def test_crafted_type_violations_fail_check(self):
        self.craft("add_line", {"id": "L0001", "doc": "D0001", "text": "副鼻腔炎かもしれない", "type": "quoted",
                                "cites": [{"source": "S0003"}]})
        self.craft("add_line", {"id": "L0002", "doc": "D0001", "text": "黄色い鼻水", "type": "document",
                                "cites": [{"source": "S0001"}]})
        code, data = self.check()
        self.assertEqual(code, 1)
        found = self.rules(data["errors"])
        self.assertIn((4, "L0001"), found)
        self.assertIn((4, "L0002"), found)


class PromotionTest(LedgerTestCase):

    def setUp(self):
        super().setUp()
        self.seed()
        # her own guess, from her own words
        self.cli("add-source", "--kind", "chat", "--text", "親知らずかも")  # S0005
        self.cli("add-line", "--doc", "D0001", "--type", "guess", "--text", "「親知らずかも」（本人の推測）",
                 "--cite", "S0005:親知らずかも")  # L0001

    def test_revising_a_guess_into_a_fact_is_refused(self):
        r = self.cli("revise-line", "--line", "L0001", "--type", "self", "--reason", "確定", ok=False)
        self.assertIn("promote", r.err)

    def test_crafted_silent_promotion_fails_check(self):
        self.craft("revise_line", {"line": "L0001", "type": "self", "reason": "確定"})
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertIn((4, "L0001"), self.rules(data["errors"]))

    def test_promote_confirmed_by_her_is_logged(self):
        r = self.cli("promote", "--line", "L0001", "--to", "self", "--confirmed-by-her")
        self.assertEqual(r.first_token, "L0001")
        ev = self.events()[-1]
        self.assertEqual(ev["op"], "promote")
        self.assertEqual(ev["actor"], "her")
        self.assertEqual(ev["data"]["confirmed_by"], "her")
        self.assertNotIn("evidence", ev["data"])
        code, data = self.check()
        self.assertEqual(code, 0, data)

    def test_promote_with_evidence_is_logged_and_cited(self):
        self.cli("add-source", "--kind", "voice", "--text", "親知らずが原因ですねって言われた")  # S0006
        self.cli("promote", "--line", "L0001", "--to", "quoted", "--evidence", "S0006:親知らずが原因ですね")
        ev = self.events()[-1]
        self.assertEqual(ev["data"]["evidence"], {"source": "S0006", "quote": "親知らずが原因ですね"})
        self.assertNotIn("confirmed_by", ev["data"])
        state_line = self.state_line("L0001")
        self.assertEqual(state_line["type"], "quoted")
        self.assertIn({"source": "S0006", "quote": "親知らずが原因ですね"}, state_line["cites"])
        code, data = self.check()
        self.assertEqual(code, 0, data)

    def test_promote_needs_exactly_one_basis(self):
        self.cli("promote", "--line", "L0001", "--to", "self", ok=False)
        self.cli("promote", "--line", "L0001", "--to", "self", "--confirmed-by-her", "--evidence", "S0001", ok=False)

    def test_promote_evidence_quote_must_be_verbatim(self):
        r = self.cli("promote", "--line", "L0001", "--to", "quoted", "--evidence", "S0003:親知らず", ok=False)
        self.assertIn("verbatim", r.err)

    def test_only_a_guess_can_be_promoted(self):
        self.cli("promote", "--line", "L0001", "--to", "self", "--confirmed-by-her")
        r = self.cli("promote", "--line", "L0001", "--to", "quoted", "--confirmed-by-her", ok=False)
        self.assertIn("guess", r.err)

    def test_demoting_to_guess_then_back_needs_a_new_promote(self):
        self.cli("promote", "--line", "L0001", "--to", "self", "--confirmed-by-her")
        self.cli("revise-line", "--line", "L0001", "--type", "guess", "--reason", "本人が取り消した")
        self.cli("revise-line", "--line", "L0001", "--type", "self", "--reason", "やっぱり", ok=False)
        self.craft("revise_line", {"line": "L0001", "type": "self", "reason": "やっぱり"})
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertIn((4, "L0001"), self.rules(data["errors"]))

    def state_line(self, line_id):
        import json
        state = json.loads(self.cli("state", "--json").out)
        for doc in state["docs"]:
            for line in doc["lines"]:
                if line["id"] == line_id:
                    return line
        raise AssertionError(line_id)


class OtherAiTest(LedgerTestCase):
    """An answer from another AI (or Claude) is a guess until promoted."""

    def setUp(self):
        super().setUp()
        self.seed()  # S0004 is other_ai (ChatGPT: 副鼻腔炎かも)

    def test_a_line_citing_an_ai_answer_must_start_as_guess(self):
        for t in ("self", "quoted", "document"):
            with self.subTest(type=t):
                r = self.cli("add-line", "--doc", "D0001", "--type", t, "--text", "副鼻腔炎かも",
                             "--cite", "S0004:副鼻腔炎かも", ok=False)
                self.assertIn("other_ai", r.err)
        self.cli("add-line", "--doc", "D0001", "--type", "guess", "--text", "ChatGPTの推測：「副鼻腔炎かも」",
                 "--cite", "S0004:副鼻腔炎かも")

    def test_crafted_fact_from_an_ai_answer_fails_check(self):
        self.craft("add_line", {"id": "L0001", "doc": "D0001", "text": "副鼻腔炎", "type": "self",
                                "cites": [{"source": "S0004", "quote": "副鼻腔炎かも"}]})
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertIn((4, "L0001"), self.rules(data["errors"]))

    def test_adding_an_ai_cite_to_a_fact_is_refused(self):
        self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "黄色い鼻水（2026-09-16）",
                 "--cite", "S0001:黄色い鼻水が出る")
        r = self.cli("revise-line", "--line", "L0001", "--cite", "S0001:黄色い鼻水が出る",
                     "--cite", "S0004:副鼻腔炎かも", "--reason", "AIの答えも出典に", ok=False)
        self.assertIn("other_ai", r.err)
        self.craft("revise_line", {"line": "L0001", "reason": "AIの答えも出典に",
                                   "cites": [{"source": "S0001", "quote": "黄色い鼻水が出る"},
                                             {"source": "S0004", "quote": "副鼻腔炎かも"}]})
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertIn((4, "L0001"), self.rules(data["errors"]))

    def test_her_confirmation_can_make_it_her_own_report(self):
        self.cli("add-line", "--doc", "D0001", "--type", "guess", "--text", "ChatGPTの推測：「副鼻腔炎かも」",
                 "--cite", "S0004:副鼻腔炎かも")
        self.cli("promote", "--line", "L0001", "--to", "self", "--confirmed-by-her")
        code, data = self.check()
        self.assertEqual(code, 0, data)

    def test_her_confirmation_cannot_make_an_ai_answer_a_doctors_word(self):
        self.cli("add-line", "--doc", "D0001", "--type", "guess", "--text", "ChatGPTの推測：「副鼻腔炎かも」",
                 "--cite", "S0004:副鼻腔炎かも")
        r = self.cli("promote", "--line", "L0001", "--to", "quoted", "--confirmed-by-her", ok=False)
        self.assertIn("quoted", r.err)

    def test_evidence_from_a_real_source_can_make_it_a_doctors_word(self):
        self.cli("add-line", "--doc", "D0001", "--type", "guess", "--text", "ChatGPTの推測：「副鼻腔炎かも」",
                 "--cite", "S0004:副鼻腔炎かも")
        self.cli("promote", "--line", "L0001", "--to", "quoted", "--evidence", "S0003:副鼻腔炎かもしれない")
        code, data = self.check()
        self.assertEqual(code, 0, data)


if __name__ == "__main__":
    unittest.main()
