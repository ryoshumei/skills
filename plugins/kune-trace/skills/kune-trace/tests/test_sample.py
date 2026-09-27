"""The fictional sample ledger (青木 美月, ENT story 9/16–9/25) passes check and is reproducible."""

import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest

from support import SAMPLE_DIR, EXAMPLES_DIR, run


def load_build_module():
    spec = importlib.util.spec_from_file_location("build_sample", str(EXAMPLES_DIR / "build_sample.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SampleLedgerTest(unittest.TestCase):

    def setUp(self):
        # check writes views/check.json, so work on a copy and leave the committed sample untouched
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="kune-trace-sample-"))
        self.copy = self.tmp / "sample-ledger"
        shutil.copytree(str(SAMPLE_DIR), str(self.copy))

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def test_sample_passes_check(self):
        r = run(["check", "--json", "--dir", self.copy])
        data = json.loads(r.out)
        self.assertEqual(r.code, 0, data)
        self.assertTrue(data["ok"])
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["warnings"], [])

    def test_sample_is_marked_as_sample(self):
        meta = json.loads((self.copy / "ledger.json").read_text(encoding="utf-8"))
        self.assertIs(meta["sample"], True)
        self.assertEqual(meta["profile"], "health-visit")

    def test_sample_tells_the_ent_story(self):
        state = json.loads(run(["state", "--json", "--dir", self.copy]).out)
        sources = {s["id"]: s for s in state["sources"]}
        self.assertEqual(sources["S0001"]["kind"], "chat")
        self.assertEqual(sources["S0001"]["text"], "鼻がつまって、黄色い鼻水が出る。頬のあたりが重い")
        self.assertEqual(sources["S0002"]["kind"], "voice")
        self.assertEqual(sources["S0003"]["kind"], "photo")
        self.assertEqual(sources["S0003"]["page"], 1)
        self.assertEqual(sources["S0004"]["kind"], "voice")
        self.assertEqual(sources["S0004"]["media_time"], "0:14")
        self.assertIn("少し良くなった気がする", sources["S0004"]["text"])
        self.assertEqual(sources["S0005"]["kind"], "other_ai")
        self.assertIn("副鼻腔炎かも", sources["S0005"]["text"])
        docs = state["docs"]
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["kind"], "visit-memo")
        lines = docs[0]["lines"]
        types = [l["type"] for l in lines]
        self.assertEqual(types.count("guess"), 1)
        for t in ("quoted", "document", "self"):
            self.assertIn(t, types)
        cited = {c["source"] for l in lines for c in l["cites"]}
        self.assertEqual(cited, {"S0001", "S0002", "S0003", "S0004", "S0005"})
        guess = [l for l in lines if l["type"] == "guess"][0]
        self.assertEqual([c["source"] for c in guess["cites"]], ["S0005"])

    def test_sample_rebuilds_byte_for_byte(self):
        build = load_build_module()
        out = self.tmp / "rebuilt"
        build.build(out)
        hint = "examples/sample-ledger differs from a fresh build: run examples/build_sample.py"
        for rel in ("ledger.json", "log.jsonl", "views/index.html"):
            with self.subTest(file=rel):
                self.assertEqual((out / rel).read_bytes(), (SAMPLE_DIR / rel).read_bytes(), "%s (%s)" % (hint, rel))
        # running `check` on the sample only moves checked_at; everything else must match
        fresh = json.loads((out / "views" / "check.json").read_text(encoding="utf-8"))
        committed = json.loads((SAMPLE_DIR / "views" / "check.json").read_text(encoding="utf-8"))
        fresh.pop("checked_at")
        committed.pop("checked_at")
        self.assertEqual(fresh, committed, hint)

    def test_committed_view_is_the_passing_check(self):
        check = json.loads((SAMPLE_DIR / "views" / "check.json").read_text(encoding="utf-8"))
        self.assertTrue(check["ok"])
        html = (SAMPLE_DIR / "views" / "index.html").read_text(encoding="utf-8")
        self.assertIn("サンプルデータ", html)
        self.assertIn("チェック：合格", html)
        self.assertIn("9/22 音声 0:14", html)
        self.assertIn("9/18 写真 p.1", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)


if __name__ == "__main__":
    unittest.main()
