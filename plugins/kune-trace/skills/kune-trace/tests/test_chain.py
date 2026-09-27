"""Rule 1: the hash chain, tamper detection, and one event per write."""

import json
import re
import unittest

from support import LedgerTestCase, expected_hash, canonical, T0

ID_RE = re.compile(r"^(S|D|L|N)\d{4,}$")


class ChainTest(LedgerTestCase):

    def test_init_writes_meta_and_empty_log(self):
        meta = json.loads((self.dir / "ledger.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["profile"], "health-visit")
        self.assertEqual(meta["timezone"], "Asia/Tokyo")
        self.assertIn("format_version", meta)
        self.assertEqual(meta["created_at"], T0)
        self.assertEqual(self.log_path().read_bytes(), b"")
        self.assertTrue((self.dir / "views").is_dir())

    def test_init_refuses_to_overwrite(self):
        r = self.cli("init", ok=False)
        self.assertIn("already", r.err)

    def test_every_write_appends_exactly_one_event_and_prints_an_id(self):
        self.seed()  # 4 sources + 1 doc
        self.assertEqual(len(self.events()), 5)
        writes = [
            ("add-line", "--doc", "D0001", "--type", "self", "--text", "黄色い鼻水が出る（2026-09-16）",
             "--cite", "S0001:黄色い鼻水が出る"),
            ("revise-line", "--line", "L0001", "--text", "黄色い鼻水：2026-09-16から", "--reason", "書き方をそろえる"),
            ("add-line", "--doc", "D0001", "--type", "guess", "--text", "ChatGPTの推測：「副鼻腔炎かも」",
             "--cite", "S0004:副鼻腔炎かも"),
            ("promote", "--line", "L0002", "--to", "self", "--confirmed-by-her"),
            ("approve", "--line", "L0001"),
            ("approve", "--doc", "D0001"),
            ("note", "--text", "本人がメモを確認した", "--about", "D0001"),
            ("add-source", "--kind", "calendar", "--text", "9/25 10:30 耳鼻科"),
            ("add-doc", "--kind", "timeline", "--title", "鼻の経過"),
        ]
        for argv in writes:
            before = len(self.events())
            r = self.cli(*argv)
            self.assertEqual(len(self.events()), before + 1, argv)
            ids = r.first_token.split(",")
            for i in ids:
                self.assertRegex(i, ID_RE, (argv, r.out))

    def test_event_shape_and_hash_formula(self):
        self.seed()
        prev = "0" * 64
        for n, (line, ev) in enumerate(zip(self.log_lines(), self.events()), start=1):
            self.assertEqual(set(ev), {"seq", "at", "actor", "op", "data", "prev", "hash"})
            self.assertEqual(ev["seq"], n)
            self.assertEqual(ev["prev"], prev)
            self.assertEqual(ev["hash"], expected_hash(ev))
            self.assertEqual(line, canonical(ev), "each line is stored in canonical form")
            self.assertRegex(ev["at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00$")
            self.assertIn(ev["actor"], ("her", "claude"))
            prev = ev["hash"]

    def test_intact_chain_passes(self):
        self.seed()
        code, data = self.check()
        self.assertEqual(code, 0, data)
        self.assertTrue(data["ok"])
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["head"]["seq"], 5)

    def _tamper(self, fn):
        raw = self.log_path().read_bytes()
        self.log_path().write_bytes(fn(raw))

    def test_editing_one_byte_of_text_fails(self):
        self.seed()
        # 黄色い -> 白色い: one character in the first source's verbatim text
        self._tamper(lambda b: b.replace("黄色い".encode("utf-8"), "白色い".encode("utf-8"), 1))
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertIn((1, None), {(e["rule"], None) for e in data["errors"]})
        self.assertTrue(any(e["id"] == "#1" for e in data["errors"]), data["errors"])

    def test_editing_one_ascii_byte_fails(self):
        self.seed()
        raw = self.log_path().read_bytes()
        i = raw.index(b'"page":1')
        tampered = raw[:i] + b'"page":2' + raw[i + len(b'"page":1'):]
        self.log_path().write_bytes(tampered)
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any(e["rule"] == 1 for e in data["errors"]))

    def test_whitespace_only_edit_fails(self):
        self.seed()
        self._tamper(lambda b: b.replace(b'"actor":', b'"actor": ', 1))
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any(e["rule"] == 1 for e in data["errors"]))

    def test_recomputed_hash_with_patched_prev_still_fails(self):
        """Rewriting an event and its own hash breaks the link to the next event."""
        self.seed()
        lines = self.log_lines()
        ev = json.loads(lines[1])
        ev["data"]["text"] = ev["data"]["text"].replace("1回1錠", "1回2錠")
        ev["hash"] = expected_hash(ev)
        lines[1] = canonical(ev)
        self.log_path().write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any(e["rule"] == 1 and e["id"] == "#3" for e in data["errors"]), data["errors"])

    def test_deleting_a_middle_line_fails(self):
        self.seed()
        lines = self.log_lines()
        del lines[2]
        self.log_path().write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any(e["rule"] == 1 for e in data["errors"]))

    def test_deleting_the_last_line_after_a_check_fails(self):
        self.seed()
        code, _ = self.check()
        self.assertEqual(code, 0)
        lines = self.log_lines()[:-1]
        self.log_path().write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        code, data = self.check()
        self.assertEqual(code, 1, data)
        self.assertTrue(any(e["rule"] == 1 and "last check" in e["message"] for e in data["errors"]))
        # the anchor is not lowered by the failing check: it keeps failing
        code, data = self.check()
        self.assertEqual(code, 1)

    def test_invalid_json_line_fails(self):
        self.seed()
        self._tamper(lambda b: b + b"{not json}\n")
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any(e["rule"] == 1 for e in data["errors"]))

    def test_missing_final_newline_fails(self):
        self.seed()
        self._tamper(lambda b: b[:-1])
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any(e["rule"] == 1 and "newline" in e["message"] for e in data["errors"]), data)

    def test_human_output_names_the_rule(self):
        self.seed()
        self._tamper(lambda b: b.replace("黄色い".encode("utf-8"), "白色い".encode("utf-8"), 1))
        r = self.cli("check", ok=False)
        self.assertEqual(r.code, 1)
        self.assertIn("chain", r.out)
        self.assertIn("FAIL", r.out)

    def test_write_on_a_broken_chain_warns(self):
        self.seed()
        self._tamper(lambda b: b.replace("黄色い".encode("utf-8"), "白色い".encode("utf-8"), 1))
        r = self.cli("add-source", "--kind", "chat", "--text", "朝だけ右の頬が痛い")
        self.assertIn("chain", r.err)

    def test_clock_going_backwards_is_a_warning(self):
        self.cli("add-source", "--kind", "chat", "--text", "一つめ", at="2026-09-24T21:00:00+09:00")
        self.cli("add-source", "--kind", "chat", "--text", "二つめ", at="2026-09-24T20:00:00+09:00")
        code, data = self.check()
        self.assertEqual(code, 0)
        self.assertTrue(any(w["rule"] == 1 for w in data["warnings"]), data)


if __name__ == "__main__":
    unittest.main()
