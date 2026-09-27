"""WALKTHROUGH.md stays true: replay its commands and compare every printed output.

In the walkthrough, each ```console block holds ``$ python3 "$K" ...`` commands
followed by their output (stdout, then stderr). An HTML comment
``<!-- clock: <ISO instant> -->`` pins the clock for the next command; each
later command runs 20 seconds after the previous one.
"""

import datetime
import pathlib
import re
import shlex
import shutil
import tempfile
import unittest

from support import EXAMPLES_DIR, run, parse_instant

WALKTHROUGH = EXAMPLES_DIR / "WALKTHROUGH.md"
CLOCK_RE = re.compile(r"^<!--\s*clock:\s*(\S+)\s*-->\s*$")
PREFIX = 'python3 "$K" '


def parse_walkthrough(text):
    """-> [(clock, argv, expected_output)] in document order."""
    steps = []
    clock = None
    in_block = False
    current = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not in_block:
            m = CLOCK_RE.match(line.strip())
            if m:
                clock = parse_instant(m.group(1))
                continue
            if line.strip() == "```console":
                in_block = True
            continue
        if line.strip() == "```":
            in_block = False
            current = None
            continue
        if line.startswith("$ "):
            cmd = line[2:]
            if not cmd.startswith(PREFIX):
                current = None  # e.g. the K=... assignment; it prints nothing
                continue
            if clock is None:
                raise AssertionError("no clock comment before: " + cmd)
            current = {"clock": clock, "argv": shlex.split(cmd[len(PREFIX):]), "out": []}
            steps.append(current)
            clock = clock + datetime.timedelta(seconds=20)
            continue
        if current is None:
            if line.strip():
                raise AssertionError("output without a command: " + line)
            continue
        current["out"].append(line)
    return steps


class WalkthroughTest(unittest.TestCase):

    def test_every_command_prints_what_the_walkthrough_shows(self):
        text = WALKTHROUGH.read_text(encoding="utf-8")
        steps = parse_walkthrough(text)
        self.assertGreaterEqual(len(steps), 10)
        project = pathlib.Path(tempfile.mkdtemp(prefix="kune-trace-walk-"))
        try:
            results = []
            for step in steps:
                r = run(step["argv"], at=step["clock"].isoformat(), cwd=project)
                got = (r.out + r.err).rstrip("\n")
                want = "\n".join(step["out"]).rstrip("\n")
                with self.subTest(argv=" ".join(step["argv"])):
                    self.assertEqual(got, want)
                results.append((step["argv"][0], r.code, got))
            checks = [(code, out) for cmd, code, out in results if cmd == "check"]
            self.assertGreaterEqual(len(checks), 2)
            self.assertEqual(checks[0][0], 1, "the first check fails (a relative date)")
            self.assertEqual(checks[-1][0], 0, "the last check passes")
            self.assertEqual(sum(1 for code, _ in checks if code == 1), 1, "check fails exactly once")
            self.assertEqual(results[-1][0], "render")
            html = (project / "kune-ledger" / "views" / "index.html").read_text(encoding="utf-8")
            # the text mock under "What the render shows" matches the real page
            for shown in ("9/23 チャット", "9/18 写真 p.1", "9/24 AIの回答", "チェック：合格",
                          "2026-09-24 21:09 実行", "推測（未確認）", "承認済み"):
                self.assertIn(shown, html)
                self.assertIn(shown, text)
            events = (project / "kune-ledger" / "log.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertIn("log.jsonl           %d events" % len(events), text)
        finally:
            shutil.rmtree(str(project), ignore_errors=True)

    def test_she_shares_three_things(self):
        steps = parse_walkthrough(WALKTHROUGH.read_text(encoding="utf-8"))
        self.assertEqual(sum(1 for s in steps if s["argv"][0] == "add-source"), 3)


if __name__ == "__main__":
    unittest.main()
