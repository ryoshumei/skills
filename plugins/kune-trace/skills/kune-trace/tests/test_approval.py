"""Rule 6: approval is hers, per line, bound to a revision, and reset by any change."""

import json
import unittest

from support import LedgerTestCase


class ApprovalTest(LedgerTestCase):

    def setUp(self):
        super().setUp()
        self.seed()
        self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "黄色い鼻水：2026-09-16から",
                 "--cite", "S0001:黄色い鼻水が出る")  # L0001
        self.cli("add-line", "--doc", "D0001", "--type", "document",
                 "--text", "カルボシステイン錠500mg「JG」：1回1錠 1日3回 毎食後",
                 "--cite", "S0002:カルボシステイン錠500mg「JG」　1回1錠　1日3回　毎食後")  # L0002

    def status(self, line_id):
        state = json.loads(self.cli("state", "--json").out)
        for doc in state["docs"]:
            for line in doc["lines"]:
                if line["id"] == line_id:
                    return line["status"], line["rev"]
        raise AssertionError(line_id)

    def test_new_lines_are_drafts_and_check_lists_them(self):
        self.assertEqual(self.status("L0001"), ("draft", 1))
        code, data = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(data["drafts"], ["L0001", "L0002"])
        self.assertIn("L0001", self.cli("check").out)

    def test_approve_a_line(self):
        r = self.cli("approve", "--line", "L0001")
        self.assertEqual(r.first_token, "L0001")
        ev = self.events()[-1]
        self.assertEqual(ev["actor"], "her")
        self.assertEqual(ev["data"]["lines"], [{"line": "L0001", "rev": 1}])
        self.assertEqual(self.status("L0001"), ("approved", 1))
        code, data = self.check()
        self.assertEqual(code, 0, data)
        self.assertEqual(data["drafts"], ["L0002"])

    def test_revision_after_approval_sets_it_back_to_draft(self):
        self.cli("approve", "--line", "L0001")
        r = self.cli("revise-line", "--line", "L0001", "--text", "黄色い鼻水：2026-09-16から続いている",
                     "--reason", "本人が言い回しを直した", "--actor", "her")
        self.assertIn("draft", r.out)
        self.assertEqual(self.status("L0001"), ("draft", 2))
        code, data = self.check()
        self.assertEqual(code, 0)
        self.assertIn("L0001", data["drafts"])
        self.cli("approve", "--line", "L0001")
        self.assertEqual(self.status("L0001"), ("approved", 2))

    def test_promotion_after_approval_sets_it_back_to_draft(self):
        self.cli("add-line", "--doc", "D0001", "--type", "guess", "--text", "ChatGPTの推測：「副鼻腔炎かも」",
                 "--cite", "S0004:副鼻腔炎かも")  # L0003
        self.cli("approve", "--line", "L0003")
        self.cli("promote", "--line", "L0003", "--to", "self", "--confirmed-by-her")
        self.assertEqual(self.status("L0003"), ("draft", 2))

    def test_approve_a_whole_doc_in_one_event(self):
        before = len(self.events())
        r = self.cli("approve", "--doc", "D0001")
        self.assertEqual(r.first_token, "L0001,L0002")
        self.assertEqual(len(self.events()), before + 1)
        self.assertEqual(self.events()[-1]["data"]["doc"], "D0001")
        code, data = self.check()
        self.assertEqual(code, 0, data)
        self.assertEqual(data["drafts"], [])

    def test_approve_needs_a_draft(self):
        self.cli("approve", "--line", "L0001")
        r = self.cli("approve", "--line", "L0001", ok=False)
        self.assertIn("already", r.err)
        self.cli("approve", "--doc", "D0001")
        self.cli("approve", "--doc", "D0001", ok=False)

    def test_claude_cannot_approve(self):
        r = self.cli("approve", "--line", "L0001", "--actor", "claude", ok=False)
        self.assertIn("her", r.err)

    def test_crafted_approval_of_a_stale_revision_fails_check(self):
        self.cli("revise-line", "--line", "L0001", "--text", "黄色い鼻水：2026-09-16から続く", "--reason", "直し")
        self.craft("approve", {"lines": [{"line": "L0001", "rev": 1}]}, actor="her")
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertIn((6, "L0001"), self.rules(data["errors"]))

    def test_crafted_approval_by_claude_fails_check(self):
        self.craft("approve", {"lines": [{"line": "L0001", "rev": 1}]}, actor="claude")
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertIn((6, "L0001"), self.rules(data["errors"]))

    def test_revision_needs_a_reason_and_a_change(self):
        self.cli("revise-line", "--line", "L0001", "--text", "黄色い鼻水", ok=False)
        self.cli("revise-line", "--line", "L0001", "--reason", "なし", ok=False)
        r = self.cli("revise-line", "--line", "L0001", "--text", "黄色い鼻水：2026-09-16から", "--reason", "同じ",
                     ok=False)
        self.assertIn("no change", r.err)

    def test_history_lists_every_event_of_the_line(self):
        self.cli("approve", "--line", "L0001")
        self.cli("revise-line", "--line", "L0001", "--text", "黄色い鼻水：2026-09-16から続いている",
                 "--reason", "本人が言い回しを直した", "--actor", "her")
        out = self.cli("history", "--line", "L0001").out
        for word in ("add_line", "approve", "revise_line", "本人が言い回しを直した", "rev 2"):
            self.assertIn(word, out)
        self.assertLess(out.index("add_line"), out.index("approve"))
        self.assertLess(out.index("approve"), out.index("revise_line"))


if __name__ == "__main__":
    unittest.main()
