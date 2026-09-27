"""Rule 5 and the clock: relative-time detection, absolute --happened-at, and ``now``."""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import support
from support import LedgerTestCase, run, SCRIPTS_DIR, ledger

RELATIVE_IN_LIST = [
    "今日", "明日", "昨日", "一昨日", "明後日", "さっき", "先ほど", "今朝", "今夜", "今晩", "昨夜", "昨晩",
    "先週", "今週", "来週", "先月", "来月",
    "3日前", "２日後", "三日前", "数日前", "この前",
    "yesterday", "today", "tomorrow", "last night", "2 days ago",
]
RELATIVE_EXTRA = ["きのう", "おととい", "けさ", "ゆうべ", "先日", "今年", "去年", "1週間前", "2か月後", "Yesterday", "this morning",
                  "何日か前", "the other day", "this afternoon", "こんやは", "きょうは", "きょうの朝", "5分前", "2時間後"]
ABSOLUTE_OK = [
    "黄色い鼻水：2026-09-16から",
    "9月18日の診察で",
    "9月18日前に受診",           # a date followed by 前 is not 「N日前」
    "1回1錠　1日3回　毎食後",      # a dose is not a relative time
    "7日分",
    "前回（9/18）からの経過",
    "朝夕食後",
    "きょうだいも同じ症状",        # siblings, not 「きょう」
    "follow-up on 2026-09-25",
    "agonist",                    # "ago" only as a word
    "こんやくしゃ",                 # 婚約者, not 「今夜」
    "2026年前半",                  # a year half, not 「N年前」
]


class RelativeWordsTest(unittest.TestCase):

    def test_every_listed_word_is_detected(self):
        for text in RELATIVE_IN_LIST + RELATIVE_EXTRA:
            with self.subTest(text=text):
                self.assertTrue(ledger.find_relative_time("症状：%s から" % text), text)

    def test_absolute_expressions_are_not_flagged(self):
        for text in ABSOLUTE_OK:
            with self.subTest(text=text):
                self.assertEqual(ledger.find_relative_time(text), [], text)

    def test_reports_the_longest_match(self):
        self.assertEqual(ledger.find_relative_time("一昨日から"), ["一昨日"])

    def test_the_documented_word_list_is_detected(self):
        """references/time.md lists the Japanese words; every one of them must be caught."""
        doc = (support.SKILL_DIR / "references" / "time.md").read_text(encoding="utf-8")
        line = [l for l in doc.splitlines() if l.startswith("- **Japanese words:**")][0]
        words = [w.strip() for w in line.split("**", 2)[2].split("、") if w.strip()]
        self.assertGreater(len(words), 30)
        for word in words:
            with self.subTest(word=word):
                self.assertEqual(ledger.find_relative_time("症状は%sから" % word), [word])


class RelativeInRecordsTest(LedgerTestCase):

    def setUp(self):
        super().setUp()
        self.seed()

    def test_relative_word_in_line_text_is_an_error(self):
        # the CLI lets it through (her confirmation may take a turn); check is the gate
        self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "右の頬の痛み：昨日から",
                 "--cite", "S0001:頬のあたりが重い")
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertIn((5, "L0001"), self.rules(data["errors"]))
        msg = [e["message"] for e in data["errors"] if e["rule"] == 5][0]
        self.assertIn("昨日", msg)

    def test_fixing_the_line_passes(self):
        self.cli("add-line", "--doc", "D0001", "--type", "self", "--text", "右の頬の痛み：昨日から",
                 "--cite", "S0001:頬のあたりが重い")
        self.cli("revise-line", "--line", "L0001", "--text", "右の頬の痛み：2026-09-23から",
                 "--reason", "「昨日」を本人が確認した日付に置き換え")
        code, data = self.check()
        self.assertEqual(code, 0, data)

    def test_relative_word_in_a_doc_title_is_an_error(self):
        self.cli("add-doc", "--kind", "visit-memo", "--title", "明日の受診メモ")
        code, data = self.check()
        self.assertEqual(code, 1)
        self.assertIn((5, "D0002"), self.rules(data["errors"]))


class RelativeInSourcesTest(LedgerTestCase):

    def test_source_with_relative_word_and_no_date_is_a_warning(self):
        self.cli("add-source", "--kind", "chat", "--text", "昨日から、朝だけ右の頬が痛い")
        code, data = self.check()
        self.assertEqual(code, 0, data)
        self.assertIn((5, "S0001"), self.rules(data["warnings"]))

    def test_unconfirmed_happened_at_still_warns(self):
        self.cli("add-source", "--kind", "chat", "--text", "昨日から、朝だけ右の頬が痛い",
                 "--happened-at", "2026-09-23")
        code, data = self.check()
        self.assertEqual(code, 0, data)
        self.assertIn((5, "S0001"), self.rules(data["warnings"]))

    def test_confirmed_happened_at_clears_the_warning(self):
        self.cli("add-source", "--kind", "chat", "--text", "昨日から、朝だけ右の頬が痛い",
                 "--happened-at", "2026-09-23", "--confirmed")
        code, data = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(data["warnings"], [])

    def test_a_note_can_confirm_the_date_later(self):
        self.cli("add-source", "--kind", "chat", "--text", "昨日から、朝だけ右の頬が痛い")
        r = self.cli("note", "--about", "S0001", "--happened-at", "2026-09-23", "--confirmed",
                     "--text", "「昨日」は2026-09-23（水）と本人が確認")
        self.assertEqual(r.first_token, "N0001")
        self.assertEqual(self.events()[-1]["actor"], "her")
        code, data = self.check()
        self.assertEqual(code, 0, data)
        self.assertEqual(data["warnings"], [])
        state = json.loads(self.cli("state", "--json").out)
        src = [s for s in state["sources"] if s["id"] == "S0001"][0]
        self.assertEqual(src["happened_at"], "2026-09-23")
        self.assertTrue(src["happened_confirmed"])
        self.assertEqual(src["text"], "昨日から、朝だけ右の頬が痛い", "the verbatim text never changes")


class HappenedAtTest(LedgerTestCase):

    def test_relative_happened_at_is_refused(self):
        for value in ["昨日", "yesterday", "today", "-1d", "9/22", "2026/09/22", "3日前", "now", ""]:
            with self.subTest(value=value):
                r = self.cli("add-source", "--kind", "chat", "--text", "頬が痛い", "--happened-at", value, ok=False)
                self.assertEqual(r.code, 2, r)
        self.assertEqual(self.events(), [])

    def test_absolute_forms_are_accepted_and_normalized(self):
        cases = [
            ("2026-09-22", "2026-09-22"),
            ("2026-09-22T08:15", "2026-09-22T08:15:00+09:00"),
            ("2026-09-22 08:15:30", "2026-09-22T08:15:30+09:00"),
            ("2026-09-22T08:15:00+09:00", "2026-09-22T08:15:00+09:00"),
            ("2026-09-21T23:15:00Z", "2026-09-21T23:15:00+00:00"),
        ]
        for value, stored in cases:
            with self.subTest(value=value):
                self.cli("add-source", "--kind", "voice", "--text", "鼻づまりは少し良くなった気がする",
                         "--happened-at", value)
                self.assertEqual(self.events()[-1]["data"]["happened_at"], stored)

    def test_impossible_date_is_refused(self):
        self.cli("add-source", "--kind", "chat", "--text", "頬が痛い", "--happened-at", "2026-02-30", ok=False)

    def test_confirmed_needs_a_date(self):
        r = self.cli("add-source", "--kind", "chat", "--text", "頬が痛い", "--confirmed", ok=False)
        self.assertIn("happened-at", r.err)


class NowTest(unittest.TestCase):

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="kune-trace-now-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def _ledger(self, tz):
        d = self.tmp / ("L" + tz.replace("/", "_").replace(":", "").replace("+", "p"))
        self.assertEqual(run(["init", "--dir", d, "--tz", tz]).code, 0)
        return d

    def test_now_uses_the_ledger_time_zone(self):
        d = self._ledger("Asia/Tokyo")
        r = run(["now", "--json", "--dir", d], at="2026-09-23T15:30:00+00:00")
        self.assertEqual(r.code, 0, r)
        data = json.loads(r.out)
        self.assertEqual(data["utc"], "2026-09-23T15:30:00+00:00")
        self.assertEqual(data["local"], "2026-09-24T00:30:00+09:00")
        self.assertEqual(data["timezone"], "Asia/Tokyo")
        self.assertEqual(data["date"], "2026-09-24")
        self.assertEqual(data["weekday"], "木")
        self.assertFalse(data["fallback"])

    def test_now_with_a_fixed_offset_ledger(self):
        d = self._ledger("+05:30")
        data = json.loads(run(["now", "--json", "--dir", d], at="2026-09-23T15:30:00+00:00").out)
        self.assertEqual(data["local"], "2026-09-23T21:00:00+05:30")
        self.assertEqual(data["weekday"], "水")

    def test_now_prints_utc_local_and_the_japanese_weekday(self):
        d = self._ledger("Asia/Tokyo")
        out = run(["now", "--dir", d], at="2026-09-24T12:00:00+00:00").out
        self.assertIn("2026-09-24T12:00:00+00:00", out)
        self.assertIn("2026-09-24T21:00:00+09:00", out)
        self.assertIn("2026年9月24日（木曜日）", out)

    def test_now_without_a_ledger_defaults_to_tokyo(self):
        data = json.loads(run(["now", "--json", "--dir", self.tmp / "none"], at="2026-09-24T12:00:00+00:00").out)
        self.assertEqual(data["timezone"], "Asia/Tokyo")
        self.assertEqual(data["local"], "2026-09-24T21:00:00+09:00")

    def test_now_days_offsets_the_local_date(self):
        d = self._ledger("Asia/Tokyo")
        data = json.loads(run(["now", "--json", "--days", "-1", "--dir", d], at="2026-09-24T12:00:00+00:00").out)
        self.assertEqual(data["target"]["date"], "2026-09-23")
        self.assertEqual(data["target"]["weekday"], "水")
        out = run(["now", "--days", "-1", "--dir", d], at="2026-09-24T12:00:00+00:00").out
        self.assertIn("2026年9月23日（水曜日）", out)

    def test_events_are_stamped_in_the_ledger_time_zone(self):
        d = self._ledger("+05:30")
        run(["add-source", "--kind", "chat", "--text", "頬が痛い", "--dir", d], at="2026-09-23T15:30:00+00:00")
        ev = json.loads((d / "log.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(ev["at"], "2026-09-23T21:00:00+05:30")

    def test_fallback_to_fixed_plus_nine_without_zone_data(self):
        d = self._ledger("Asia/Tokyo")

        def missing(key):
            raise ledger.ZoneInfoNotFoundError("No time zone found with key %s" % key)

        with mock.patch.object(ledger, "ZoneInfo", side_effect=missing):
            r = run(["now", "--json", "--dir", d], at="2026-09-24T12:00:00+00:00")
            data = json.loads(r.out)
            self.assertEqual(data["local"], "2026-09-24T21:00:00+09:00")
            self.assertTrue(data["fallback"])
            human = run(["now", "--dir", d], at="2026-09-24T12:00:00+00:00").out
            self.assertIn("+09:00", human)
            self.assertIn("zoneinfo", human)

    def test_fallback_in_a_real_process_without_zone_data(self):
        try:
            import tzdata  # noqa: F401
            self.skipTest("the tzdata package is installed, so zone data can't be hidden")
        except ImportError:
            pass
        empty = self.tmp / "no-zoneinfo"
        empty.mkdir()
        env = dict(os.environ, PYTHONTZPATH=str(empty))
        p = subprocess.run([sys.executable, str(SCRIPTS_DIR / "ledger.py"), "now", "--json",
                            "--dir", str(self.tmp / "none")], capture_output=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        data = json.loads(p.stdout.decode("utf-8"))
        self.assertTrue(data["fallback"])
        self.assertTrue(data["local"].endswith("+09:00"))

    def test_other_zones_without_data_fail_loudly(self):
        def missing(key):
            raise ledger.ZoneInfoNotFoundError(key)

        with mock.patch.object(ledger, "ZoneInfo", side_effect=missing):
            r = run(["init", "--dir", self.tmp / "ny", "--tz", "America/New_York"])
            self.assertEqual(r.code, 2)
            self.assertIn("America/New_York", r.err)

    def test_unknown_zone_is_refused(self):
        r = run(["init", "--dir", self.tmp / "bad", "--tz", "Mars/Olympus"])
        self.assertEqual(r.code, 2)


if __name__ == "__main__":
    unittest.main()
