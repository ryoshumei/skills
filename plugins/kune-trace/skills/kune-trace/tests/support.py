"""Shared helpers for the kune-trace tests (standard library only).

The CLI runs in-process through ``ledger.main(argv)``, with the clock pinned
to a given instant by replacing ``ledger.system_now``. That is the only seam:
the scripts themselves always read the system clock.
"""

import contextlib
import datetime as _dt
import hashlib
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
EXAMPLES_DIR = SKILL_DIR / "examples"
SAMPLE_DIR = EXAMPLES_DIR / "sample-ledger"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ledger  # noqa: E402  (after the path tweak)

T0 = "2026-09-24T21:00:00+09:00"


def parse_instant(text):
    """ISO 8601 with offset -> aware datetime (test side, independent of ledger.py)."""
    return _dt.datetime.strptime(text.replace("Z", "+00:00"), "%Y-%m-%dT%H:%M:%S%z")


class Result:
    def __init__(self, code, out, err):
        self.code = code
        self.out = out
        self.err = err

    @property
    def first_token(self):
        return self.out.split()[0] if self.out.split() else ""

    def __repr__(self):
        return "Result(code=%r, out=%r, err=%r)" % (self.code, self.out, self.err)


def run(argv, at=T0, stdin_bytes=None, cwd=None):
    """Run the CLI in-process with the clock pinned to ``at``."""
    fixed = parse_instant(at) if at else None
    saved_now = ledger.system_now
    saved_stdin = sys.stdin
    saved_cwd = os.getcwd()
    out, err = io.StringIO(), io.StringIO()
    try:
        if fixed is not None:
            ledger.system_now = lambda: fixed
        if stdin_bytes is not None:
            sys.stdin = io.TextIOWrapper(io.BytesIO(stdin_bytes), encoding="utf-8")
        if cwd is not None:
            os.chdir(str(cwd))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ledger.main([str(a) for a in argv])
    finally:
        ledger.system_now = saved_now
        sys.stdin = saved_stdin
        os.chdir(saved_cwd)
    return Result(code, out.getvalue(), err.getvalue())


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def expected_hash(event):
    """The documented formula: sha256(prev + canonical JSON of the rest)."""
    rest = {k: v for k, v in event.items() if k not in ("prev", "hash")}
    return hashlib.sha256((event["prev"] + canonical(rest)).encode("utf-8")).hexdigest()


class LedgerTestCase(unittest.TestCase):
    """A fresh temp folder per test; ``self.dir`` is the ledger folder."""

    tz = "Asia/Tokyo"
    sample = False

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="kune-trace-test-"))
        self.dir = self.tmp / "kune-ledger"
        argv = ["init", "--dir", self.dir, "--tz", self.tz]
        if self.sample:
            argv.append("--sample")
        r = run(argv)
        self.assertEqual(r.code, 0, r)

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    # -- helpers -------------------------------------------------------
    def cli(self, *argv, at=T0, stdin_bytes=None, ok=True):
        """Run a command against this ledger (``--dir`` is added)."""
        r = run(list(argv) + ["--dir", self.dir], at=at, stdin_bytes=stdin_bytes)
        if ok is True:
            self.assertEqual(r.code, 0, r)
        elif ok is False:
            self.assertNotEqual(r.code, 0, r)
        return r

    def log_path(self):
        return self.dir / "log.jsonl"

    def log_lines(self):
        return self.log_path().read_bytes().decode("utf-8").splitlines()

    def events(self):
        return [json.loads(line) for line in self.log_lines()]

    def check(self, *extra, at=T0):
        r = run(["check", "--json", "--dir", self.dir] + list(extra), at=at)
        data = json.loads(r.out)
        return r.code, data

    def rules(self, items):
        return sorted({(i["rule"], i.get("id")) for i in items})

    def craft(self, op, data, actor="claude", at=T0):
        """Append a hash-chained event without the CLI's validation."""
        return ledger.append_event(self.dir, actor, op, data, at=parse_instant(at))

    # a small starter set: one chat, one photo, one voice, one AI answer, one memo
    def seed(self):
        self.cli("add-source", "--kind", "chat", "--text", "鼻がつまって、黄色い鼻水が出る。頬のあたりが重い")  # S0001
        self.cli("add-source", "--kind", "photo", "--text",
                 "カルボシステイン錠500mg「JG」　1回1錠　1日3回　毎食後",
                 "--file", "photos/yakujo.jpg", "--page", "1",
                 "--happened-at", "2026-09-18", "--confirmed")  # S0002
        self.cli("add-source", "--kind", "voice", "--text",
                 "副鼻腔炎かもしれないって。アレルギー性鼻炎もあるって。",
                 "--media-time", "0:03")  # S0003
        self.cli("add-source", "--kind", "other_ai", "--speaker", "ChatGPT",
                 "--text", "副鼻腔炎かも")  # S0004
        self.cli("add-doc", "--kind", "visit-memo", "--title", "受診メモ（2026-09-25）")  # D0001
