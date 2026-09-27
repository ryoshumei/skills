# Walkthrough: one evening, three things she shares

Fictional sample data: 青木 美月 is not a real person, and the clinic, the pharmacy and every word below are invented.

The evening before her ear-nose-throat revisit (Thursday 2026-09-24), she opens her project folder in Claude. There is no ledger in it yet. Every output below is what these exact commands print; `tests/test_walkthrough.py` replays them with the clock set to that evening (21:00 to 21:10, Asia/Tokyo) and fails if any output changes.

`K` is this skill's `scripts/ledger.py`. On Windows, use `py -3` (or `python`) for `python3`, and set it in PowerShell with `$K = "<skill-dir>\scripts\ledger.py"`.

```console
$ K="<skill-dir>/scripts/ledger.py"
```

## 1. She shares three things

> 明日の耳鼻科に持っていくメモを作りたい。昨日から、朝だけ右の頬が痛い。
> あと、9/18にもらった薬の説明書の写真を送るね。
> それと、ChatGPTの答えも残しておいて：「副鼻腔炎かも」

Claude creates the ledger in her folder, then reads the clock before it turns 「昨日」 into a date:

<!-- clock: 2026-09-24T21:00:00+09:00 -->
```console
$ python3 "$K" init
initialized kune-ledger (profile health-visit, time zone Asia/Tokyo)
$ python3 "$K" now --days -1
utc      2026-09-24T12:00:20+00:00
local    2026-09-24T21:00:20+09:00 (Asia/Tokyo)
date     2026-09-24 木 2026年9月24日（木曜日）
target   2026-09-23 水 2026年9月23日（水曜日） (-1 day)
```

Claude asks her to confirm, and reads back the photo's text:

> 「昨日」は 9月23日（水）のことですね？
> 写真はこう読み取りました：「みなと調剤薬局　調剤日 2026年9月18日　カルボシステイン錠500mg「JG」　1回1錠　1日3回　毎食後　7日分」。合っていますか？

> うん、どっちも合ってる。

Claude records the three things as sources. Her words stay exactly as she wrote them, 「昨日」 included, next to the date she confirmed. The 薬の説明書's date is printed on it. ChatGPT's answer is an AI answer (`other_ai`), so any line that cites it starts as a guess.

<!-- clock: 2026-09-24T21:02:00+09:00 -->
```console
$ python3 "$K" add-source --kind chat --text "昨日から、朝だけ右の頬が痛い" --happened-at 2026-09-23 --confirmed
S0001  (add_source #1, 2026-09-24T21:02:00+09:00)
$ python3 "$K" add-source --kind photo --file photos/yakujo-0918.jpg --page 1 --happened-at 2026-09-18 --confirmed --text "みなと調剤薬局　調剤日 2026年9月18日　カルボシステイン錠500mg「JG」　1回1錠　1日3回　毎食後　7日分"
S0002  (add_source #2, 2026-09-24T21:02:20+09:00)
$ python3 "$K" add-source --kind other_ai --speaker ChatGPT --text "副鼻腔炎かも"
S0003  (add_source #3, 2026-09-24T21:02:40+09:00)
```

## 2. Claude drafts the memo, and `check` fails once

Each line cites its source, with a verbatim quote where it helps. Claude copies 「昨日」 into the first line by mistake:

<!-- clock: 2026-09-24T21:04:00+09:00 -->
```console
$ python3 "$K" add-doc --kind visit-memo --title "みなと耳鼻咽喉科 2026-09-25（金）10:30" --for "佐々木先生"
D0001  (add_doc #4, 2026-09-24T21:04:00+09:00)
$ python3 "$K" add-line --doc D0001 --type self --text "右の頬の痛み：昨日から、朝だけ" --cite "S0001:朝だけ右の頬が痛い"
L0001  (add_line #5, 2026-09-24T21:04:20+09:00)
$ python3 "$K" add-line --doc D0001 --type document --text "服用中：カルボシステイン錠500mg「JG」 1回1錠 1日3回 毎食後" --cite "S0002:カルボシステイン錠500mg「JG」　1回1錠　1日3回　毎食後"
L0002  (add_line #6, 2026-09-24T21:04:40+09:00)
$ python3 "$K" add-line --doc D0001 --type guess --text "ChatGPTの推測：「副鼻腔炎かも」（未確認）" --cite "S0003:副鼻腔炎かも"
L0003  (add_line #7, 2026-09-24T21:05:00+09:00)
$ python3 "$K" check
check kune-ledger: 7 events, 3 sources, 1 doc, 3 lines (head #7 bb8876cd)
error    rule 5 time     L0001  relative time 「昨日」 in the line text. Records need absolute dates. Convert it with `ledger.py now` (or `now --days N`), confirm the date with her, then revise-line.
drafts   L0001, L0002, L0003 (not approved by her yet)
result   FAIL (1 error, 0 warnings)
```

「昨日」 is fine in her source, which keeps her words, but a record line needs the date: read tomorrow, 「昨日」 would mean 9/24. Claude fixes the line with a new event. The first text stays in the line's history, with the reason:

<!-- clock: 2026-09-24T21:06:00+09:00 -->
```console
$ python3 "$K" revise-line --line L0001 --text "右の頬の痛み：9/23から、朝だけ" --reason "「昨日」を本人が確認した日付（2026-09-23）に置き換え"
L0001  rev 2, draft  (revise_line #8, 2026-09-24T21:06:00+09:00)
$ python3 "$K" check
check kune-ledger: 8 events, 3 sources, 1 doc, 3 lines (head #8 4d15759f)
drafts   L0001, L0002, L0003 (not approved by her yet)
result   PASS (0 errors, 0 warnings)
$ python3 "$K" history --line L0001
L0001  self (本人)  draft  rev 2  in D0001
#5    2026-09-24T21:04:20+09:00  claude  add_line     rev 1: self 「右の頬の痛み：昨日から、朝だけ」 cites S0001 "朝だけ右の頬が痛い"
#8    2026-09-24T21:06:00+09:00  claude  revise_line  rev 2: text 「右の頬の痛み：9/23から、朝だけ」; reason: 「昨日」を本人が確認した日付（2026-09-23）に置き換え
```

## 3. She approves, and Claude renders the view

Claude shows her the three lines as they will read. She answers 「これでいい。ChatGPTのは推測のままで」, so Claude records her approval (never its own), checks again, and renders:

<!-- clock: 2026-09-24T21:09:00+09:00 -->
```console
$ python3 "$K" approve --doc D0001
L0001,L0002,L0003  approved  (approve #9, 2026-09-24T21:09:00+09:00)
$ python3 "$K" check
check kune-ledger: 9 events, 3 sources, 1 doc, 3 lines (head #9 8baba58a)
result   PASS (0 errors, 0 warnings)
$ python3 "$K" render
wrote kune-ledger/views/index.html
```

## What the render shows

`kune-ledger/views/index.html` is one file with no network access. Claude gives her its path (on claude.ai, the file itself) and doesn't publish it anywhere. On her phone it reads like this:

```text
みなと耳鼻咽喉科 2026-09-25（金）10:30
受診メモ・宛先：佐々木先生
チェック：合格（2026-09-24 21:09 実行）
表示の作成：2026-09-24 21:09・時刻は Asia/Tokyo（+09:00）

[本人] 承認済み                                    L0001
右の頬の痛み：9/23から、朝だけ
( 9/23 チャット )

[書類] 承認済み                                    L0002
服用中：カルボシステイン錠500mg「JG」 1回1錠 1日3回 毎食後
( 9/18 写真 p.1 )

[推測（未確認）] 承認済み          (dashed border)  L0003
ChatGPTの推測：「副鼻腔炎かも」（未確認）
( 9/24 AIの回答 )
```

Tapping 「9/23 チャット」 opens the source: her words 「昨日から、朝だけ右の頬が痛い」 with 「朝だけ右の頬が痛い」 highlighted, the kind (チャット), when it was recorded (2026-09-24 21:02), when it happened (2026-09-23（水）・確認済み), and the line's history: created by Claude with 「昨日から」, revised with the reason above, approved by her.

Her folder now holds:

```text
kune-ledger/
  ledger.json         meta (profile, time zone, created_at)
  log.jsonl           9 events, hash-chained
  views/check.json    the last check result
  views/index.html    the view above
```
