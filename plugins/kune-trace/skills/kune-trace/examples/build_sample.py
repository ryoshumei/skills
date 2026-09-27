#!/usr/bin/env python3
"""Build examples/sample-ledger by running the real CLI, so its chain is real.

FICTIONAL SAMPLE DATA. 青木 美月 is not a real person; the clinic, the
pharmacy and every word below are invented (they come from the KUNE UX
prototype's scripted ENT story, 2026-09-16 to 2026-09-25).

Each step is one ``ledger.py`` command, run in-process with the clock pinned
to the story's time, so the build is reproducible byte for byte. That pin
exists only here and in the tests; in a real ledger every time comes from the
system clock.

    python3 build_sample.py            # rebuild examples/sample-ledger
    python3 build_sample.py --out DIR  # build somewhere else
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import ledger  # noqa: E402

DEFAULT_OUT = HERE / "sample-ledger"
JST = dt.timezone(dt.timedelta(hours=9))

YAKUJO_0918 = "\n".join([
    "薬剤情報提供書",
    "みなと調剤薬局　調剤日 2026年9月18日",
    "処方医：みなと耳鼻咽喉科　佐々木",
    "カルボシステイン錠500mg「JG」　1回1錠　1日3回　毎食後　7日分",
    "痰や鼻水を出しやすくする",
    "フェキソフェナジン塩酸塩錠60mg「NP」　1回1錠　1日2回　朝夕食後　7日分",
    "アレルギーを抑える",
])

# (story time in JST, argv) - the commands Claude would have run, in order.
STEPS = [
    ("2026-09-16 21:04:00", ["init", "--sample"]),
    # 9/16 21:04 her first note about her nose (chat)                                    -> S0001
    ("2026-09-16 21:04:40", ["add-source", "--kind", "chat",
                             "--text", "鼻がつまって、黄色い鼻水が出る。頬のあたりが重い"]),
    # 9/18 her voice debrief right after the first visit, with the doctor's words       -> S0002
    ("2026-09-18 11:03:10", ["add-source", "--kind", "voice", "--speaker", "本人",
                             "--text", "副鼻腔炎かもしれないって。アレルギー性鼻炎もあるって。"
                                       "痰を出しやすくする薬と、アレルギーの薬が出た",
                             "--file", "voice/2026-09-18-debrief.m4a",
                             "--happened-at", "2026-09-18", "--confirmed"]),
    # 9/18 the 薬剤情報提供書 (薬情), photographed and transcribed; she checked the text  -> S0003
    ("2026-09-18 11:31:05", ["add-source", "--kind", "photo", "--stdin",
                             "--file", "photos/2026-09-18-yakujo.jpg", "--page", "1",
                             "--happened-at", "2026-09-18", "--confirmed"]),
    # 9/22 her voice memo; the part at 0:14                                             -> S0004
    ("2026-09-22 08:16:10", ["add-source", "--kind", "voice", "--speaker", "本人",
                             "--text", "鼻づまりは少し良くなった気がする。でも黄色い鼻水はまだ出る",
                             "--file", "voice/2026-09-22-memo.m4a", "--media-time", "0:14"]),
    # 9/22 ChatGPT's remark, which she wanted kept: an AI answer                       -> S0005
    ("2026-09-22 20:41:30", ["add-source", "--kind", "other_ai", "--speaker", "ChatGPT",
                             "--text", "副鼻腔炎かも"]),
    # 9/24 the memo for the 9/25 revisit                                               -> D0001
    ("2026-09-24 21:00:00", ["add-doc", "--kind", "visit-memo",
                             "--title", "みなと耳鼻咽喉科 2026-09-25（金）10:30 再診",
                             "--for", "佐々木先生"]),
    ("2026-09-24 21:00:40", ["add-line", "--doc", "D0001", "--type", "self",
                             "--text", "黄色い鼻水：9/16に記録、9/22も「まだ出る」",
                             "--cite", "S0001:黄色い鼻水が出る", "--cite", "S0004:黄色い鼻水はまだ出る"]),
    # Claude's first draft overstates her words (少し -> かなり); she corrects it below
    ("2026-09-24 21:01:10", ["add-line", "--doc", "D0001", "--type", "self",
                             "--text", "鼻づまり：かなり改善", "--cite", "S0004"]),
    ("2026-09-24 21:01:40", ["add-line", "--doc", "D0001", "--type", "quoted",
                             "--text", "前回（9/18）の先生の言葉：「副鼻腔炎かもしれない」「アレルギー性鼻炎もある」",
                             "--cite", "S0002:副鼻腔炎かもしれない", "--cite", "S0002:アレルギー性鼻炎もある"]),
    ("2026-09-24 21:02:10", ["add-line", "--doc", "D0001", "--type", "document",
                             "--text", "服用中：カルボシステイン錠500mg「JG」 1回1錠 1日3回 毎食後（9/18の薬情）",
                             "--cite", "S0003:カルボシステイン錠500mg「JG」　1回1錠　1日3回　毎食後"]),
    ("2026-09-24 21:02:40", ["add-line", "--doc", "D0001", "--type", "document",
                             "--text", "服用中：フェキソフェナジン塩酸塩錠60mg「NP」 1回1錠 1日2回 朝夕食後（9/18の薬情）",
                             "--cite", "S0003:フェキソフェナジン塩酸塩錠60mg「NP」　1回1錠　1日2回　朝夕食後"]),
    ("2026-09-24 21:05:00", ["revise-line", "--line", "L0002", "--actor", "her",
                             "--text", "鼻づまり：「少し良くなった気がする」（9/22）",
                             "--cite", "S0004:少し良くなった気がする",
                             "--reason", "本人の言葉は「少し良くなった気がする」。程度を強めない（少し→かなり）"]),
    # she reads the five lines and approves them
    ("2026-09-24 21:06:30", ["approve", "--doc", "D0001"]),
    # then asks to keep ChatGPT's remark in the memo as a guess; she decides at the clinic whether to show it
    ("2026-09-24 21:07:30", ["add-line", "--doc", "D0001", "--type", "guess",
                             "--text", "ChatGPTの推測：「副鼻腔炎かも」（9/22・未確認）",
                             "--cite", "S0005:副鼻腔炎かも"]),
    ("2026-09-24 21:08:00", ["check"]),
    ("2026-09-24 21:08:20", ["render"]),
]

STDIN = {"S0003": YAKUJO_0918}


def at(stamp):
    return dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)


def run(argv, when, stdin_text=None):
    """One CLI command, in-process, with the clock pinned to ``when``."""
    saved_now, saved_stdin = ledger.system_now, sys.stdin
    out = io.StringIO()
    try:
        ledger.system_now = lambda: when
        if stdin_text is not None:
            sys.stdin = io.TextIOWrapper(io.BytesIO(stdin_text.encode("utf-8")), encoding="utf-8")
        with contextlib.redirect_stdout(out):
            code = ledger.main(argv)
    finally:
        ledger.system_now, sys.stdin = saved_now, saved_stdin
    if code != 0:
        raise SystemExit("step failed (%s): %s\n%s" % (code, " ".join(argv), out.getvalue()))
    return out.getvalue()


def build(out_dir, verbose=False):
    out_dir = Path(out_dir)
    if out_dir.exists():
        meta = out_dir / "ledger.json"
        if not meta.exists() or '"sample": true' not in meta.read_text(encoding="utf-8"):
            raise SystemExit("%s exists and is not a sample ledger; not touching it" % out_dir)
        shutil.rmtree(str(out_dir))
    next_source = 1
    for stamp, argv in STEPS:
        stdin_text = None
        if argv[0] == "add-source":
            sid = "S%04d" % next_source
            next_source += 1
            stdin_text = STDIN.get(sid)
        printed = run(argv + ["--dir", str(out_dir)], at(stamp), stdin_text)
        if verbose:
            sys.stdout.write("$ ledger.py %s\n%s" % (" ".join(argv), printed))
    return out_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()
    build(args.out, verbose=not args.quiet)


if __name__ == "__main__":
    main()
