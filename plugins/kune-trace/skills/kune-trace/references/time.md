# Time

For a health record, the timeline *is* the fact: when a symptom started, when a medicine began, which visit said what. Models are unreliable about "now": they mix up dates and weekdays and invent appointments. So the ledger takes every time from the system clock and keeps records in absolute dates.

## The only source of "now"

```console
$ python3 <skill-dir>/scripts/ledger.py now --days -1
utc      2026-09-24T12:00:20+00:00
local    2026-09-24T21:00:20+09:00 (Asia/Tokyo)
date     2026-09-24 木 2026年9月24日（木曜日）
target   2026-09-23 水 2026年9月23日（水曜日） (-1 day)
```

- Run `now` at the start of every session and before any date arithmetic. Use its date and weekday, never your own idea of today.
- Use `now --days N` for 「昨日」 (`-1`), 「一昨日」 (`-2`), 「3日前」 (`-3`), 「明日」 (`1`), and so on. It prints the weekday too, so you never compute a weekday in your head. For 「先週の金曜」, find the offset from today's weekday, then confirm the result with `now --days N`.
- Never state a date, a weekday or an appointment that doesn't come from `now` or from a source in the ledger. If you don't know, say so.

Every event's `at` is written by the script from the same clock, in the ledger's time zone, as ISO 8601 with its UTC offset (`2026-09-24T21:02:00+09:00`).

## Time zone

- The ledger's time zone is set by `init --tz` and stored in `ledger.json`. The default is `Asia/Tokyo`. An IANA name or a fixed offset such as `+09:00` both work.
- `now` uses the ledger's time zone. Without a ledger it uses Asia/Tokyo, and `--tz` overrides both.
- **Fallback:** some machines have no time zone data (Windows without the `tzdata` package, for example). There, Asia/Tokyo falls back to the fixed offset `+09:00`, which is exact because Japan has no daylight saving time, and `now` prints a note saying so. Any other named zone without data is refused: use a fixed offset such as `--tz +01:00`, or install `tzdata`.

## Two times per source

| Time | Where | Meaning |
|---|---|---|
| captured | the `add_source` event's `at` | when she shared it and it was recorded; always from the clock |
| `happened_at` | the source's data | when the thing happened, when that differs (the day the pain started, the date on a 薬情, the visit a debrief is about) |

`happened_at` is only ever absolute: `2026-09-23`, or `2026-09-22T08:15` (which gets the ledger's offset), or a datetime with its own offset. The script refuses anything relative or partial (`昨日`, `yesterday`, `9/22`, `-1d`). `happened_confirmed` records whether she confirmed it, or it is printed on the document itself. The view shows it as 確認済み or 未確認.

## Converting a relative date

1. She says: 「昨日から、朝だけ右の頬が痛い」.
2. Run `now --days -1`, which gives `2026-09-23 水`.
3. Ask, with the weekday: 「昨日」は9月23日（水）のことですね？
4. When she confirms, record her words unchanged with the date:
   `add-source --kind chat --text "昨日から、朝だけ右の頬が痛い" --happened-at 2026-09-23 --confirmed`
5. Write the record line with the absolute date: 「右の頬の痛み：9/23から、朝だけ」.

If she doesn't answer yet, record the source without `--happened-at`; `check` will warn about it. When she confirms later, add the date with `note --about S0001 --happened-at 2026-09-23 --confirmed --text "「昨日」は2026-09-23（水）と本人が確認"`.

**Late at night, always ask.** Between midnight and about 4:00, 「今日」 and 「昨日」 often mean the day before the calendar date: at 01:30 on 9/25, 「今日の夜」 usually means the evening of 9/24. Ask which date she means instead of converting.

## Records use absolute dates; sources keep her words

- **Line text, doc titles and `for`:** no relative time words. Write `9/23` or `2026-09-23`. A line read next week must still be true, and 「昨日から」 in a memo read on 9/25 would point to 9/24. `check` rule 5 reports these as errors.
- **Source text:** verbatim, so it may contain 「昨日」. If it does and the source has no confirmed `happened_at`, `check` warns: the date is still unanchored.

## Words `check` detects

Detection is a heuristic, written to be strict. It covers:

- **Japanese words:** 今日、本日、明日、昨日、一昨日、明後日、さっき、先ほど、先程、さきほど、今朝、今夜、今晩、昨夜、昨晩、明朝、昨朝、先週、今週、来週、再来週、先々週、先月、今月、来月、再来月、先々月、去年、昨年、今年、来年、一昨年、おととし、この前、このあいだ、先日
- **Hiragana forms:** きのう、おととい、おとつい、あさって、あした、けさ、ゆうべ, こんや (not こんやく), and きょう only before a particle or punctuation (きょうは, きょうの, きょうから: not きょうだい)
- **Counts:** a number or 数/何 with 日, 週, 週間, か月 (ヶ月, カ月), 年, 時間 or 分, followed by 前 or 後: 3日前, ２日後, 三日前, 数日前, 1週間前, 2か月後, 何日か前. A calendar date is not a count, so 9月18日前 isn't matched, and neither are a dose (1日3回) or a supply (7日分).
- **English:** yesterday, today, tonight, tomorrow, last night, the other day, this morning, this afternoon, this evening, this week, month or year, last or next week, month or year, and `ago` (2 days ago).

If a correct line is flagged, rephrase it with an absolute date; don't try to get around the check. 前回 and 次回 (the previous and next visit) aren't flagged, but give the date anyway when you know it: 前回（9/18）.
