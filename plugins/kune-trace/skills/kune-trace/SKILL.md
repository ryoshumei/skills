---
name: kune-trace
description: "Keep traceable records of the health information a person shares in conversation: their messages, voice notes, photos of prescriptions or medicine leaflets, what their doctor said, and answers from other AIs. Every source is stored verbatim in a local, append-only, hash-chained ledger in their folder. Every line of a record or visit memo cites its sources and carries a claim type (a doctor's words, a document, their own report, or an unconfirmed guess), and every date comes from the clock, never from memory. Use it whenever the user shares health information they want kept (記録して, 残しておいて), asks to prepare a memo for a doctor's visit (受診メモ, 先生に渡すメモ), asks where a fact came from (どこで言ってた？, 出典は？), wants a timeline of their symptoms, medicines or visits (経過, 時系列), or corrects something in their record (訂正して, 直して), even if they never name the skill. It organizes and traces their own records and adds no medical judgement of its own."
---

# kune-trace: records where every line cites its source

People keep their health in long chats, and three things go wrong: facts get scattered and nobody can find where one came from, guesses quietly turn into facts, and dates drift ("yesterday" said on Tuesday, read on Friday). This skill keeps a ledger in her folder instead. Every message, photo, document and quoted doctor's word she shares becomes a source, stored verbatim with the time from the clock. Every line of a record or 受診メモ cites those sources and says what kind of claim it is. Nothing is ever edited in place: every change is a new, hash-chained event, so the history shows who changed what, when and why.

*She* below means the person whose record it is (the log's actor `her`). `<skill-dir>` is this skill's folder. Run everything through one script, which needs Python 3.9+ and nothing else:

```bash
python3 <skill-dir>/scripts/ledger.py <command> [--dir kune-ledger]
```

On Windows use `py -3` (or `python`) for `python3`. The ledger folder defaults to `kune-ledger/` in the current folder.

## The one safety line

If something she says may be an emergency, respond to her safety first, as you normally would; record it afterwards. Never file an emergency away silently.

## Principles

1. **Every line is traceable.** A line cites at least one source (`--cite S0003`), with the exact words when they matter (`--cite "S0003:少し良くなった気がする"`). If no source says it, it doesn't go in the record.
2. **Her words stay verbatim.** A source holds exactly what she said or wrote, and a photo or document holds exactly what is printed on it. Don't tidy, shorten or strengthen: 「少し良くなった気がする」 must not become 「改善」, because the doctor reads the memo as her own account. Quote her in the line when the wording carries meaning.
3. **Every line has a claim type.** Choose it by where the words came from, not by how sure they sound:

   | Code | Label (health-visit) | Use for |
   |---|---|---|
   | `quoted` | 医師の言葉 | another person's words, quoted verbatim from a source (the doctor's words as she recorded them) |
   | `document` | 書類 | what is written on a prescription, a 薬の説明書 (薬情), a test result |
   | `self` | 本人 | her own report |
   | `guess` | 推測（未確認） | anything unconfirmed, hers or an AI's |

   Details and edge cases: [references/claim-types.md](references/claim-types.md).
4. **A guess never becomes a fact silently.** An answer from another AI, including your own earlier answers, is a source of kind `other_ai`, and any line citing it is a `guess`. Only `promote` changes a guess into another type, and it needs either a source that supports it (`--evidence "S0007:..."`) or her explicit confirmation (`--confirmed-by-her`). The log keeps which. Tell her when you promote.
5. **Time only from `ledger.py now`.** Never state today's date, a weekday or a time from memory. Run `now` at the start of a session and before any date arithmetic; `now --days -1` gives yesterday's date and weekday.
6. **Relative dates are converted and confirmed.** When she says 「昨日」 or 「3日前」, compute the date with `now --days N`, ask her (「昨日」は9月23日（水）のことですね？), and record it with `--happened-at 2026-09-23 --confirmed`. Her source keeps her words; record lines use the absolute date. Details: [references/time.md](references/time.md).
7. **Corrections are new events, never edits.** Never open `log.jsonl` or `ledger.json` with an editor or a file tool; any hand edit breaks the chain and `check` fails. Fix a line with `revise-line --reason`. If a source was recorded wrong (say, a misread photo), add the corrected source, `note --about` the old one, and revise the lines to cite the new one.
8. **Only she approves.** Show her the exact text of the lines, and run `approve` only after she says yes to it. Any later change to a line sends it back to draft (下書き) until she approves again.

## Setup per surface

- **Claude desktop:** her project is a folder on her computer, and the ledger lives in it as `kune-ledger/`. On first use, run `init`, then ask her to confirm that `kune-ledger/ledger.json` appeared in her folder. Writing to that folder is expected to work, but check it once.
- **Claude Code:** the working directory is her folder, and the ledger is `./kune-ledger/`. If the folder is a Git repository, suggest adding `kune-ledger/` to `.gitignore` before anything could commit it: a private repository is still a copy somewhere else.
- **claude.ai Project:** only she can add files to a Project. Copy her `ledger.json` and `log.jsonl` into a `kune-ledger/` folder in your sandbox and work there. After any write, give her the changed files and say plainly which ones changed: 「記録ファイル（log.jsonl）を更新しました。プロジェクトの古いファイルを、このファイルに置き換えてください。」 Until she replaces it, the Project holds the old version. So at the start of each session, run `state` and tell her when the ledger last changed (the time of its last event), for example 「この記録の最終更新は 9/24 21:08 です」, so she can tell whether it is the latest.

## Workflow

### 1. Record sources as she shares them

```bash
python3 <skill-dir>/scripts/ledger.py now
python3 <skill-dir>/scripts/ledger.py add-source --kind chat --text "昨日から、朝だけ右の頬が痛い" --happened-at 2026-09-23 --confirmed
python3 <skill-dir>/scripts/ledger.py add-source --kind photo --file photos/yakujo.jpg --page 1 --happened-at 2026-09-18 --confirmed --stdin <<'EOF'
みなと調剤薬局　調剤日 2026年9月18日
カルボシステイン錠500mg「JG」　1回1錠　1日3回　毎食後　7日分
EOF
python3 <skill-dir>/scripts/ledger.py add-source --kind other_ai --speaker ChatGPT --text "副鼻腔炎かも"
```

- **Kinds:** `chat` (her messages), `voice` (a transcription; `--media-time 0:14` for where the part starts), `photo` and `document` (a transcription of what is printed; `--page`), `calendar`, and `other_ai` (an AI's answer she wants kept).
- **Transcriptions:** transcribe photos and recordings exactly, show her the text, and record it after she confirms it.
- **Files:** `--file` names the photo or recording in her folder. Long or multi-line text goes through `--stdin` (UTF-8) instead of `--text`, fed by a heredoc as above, so no temporary file with her words is left behind.
- **Dates:** `--happened-at` takes only an absolute date or datetime. Add `--confirmed` when she confirmed it or it is printed on the document.
- **IDs:** each command prints the new id (`S0001`) first. Lines cite that id.
- **Choice:** she decides what is kept. When it's unclear whether she wants something recorded (a passing remark, someone else's information), ask first.

### 2. Build a memo (or a record, or a timeline) with cites

```bash
python3 <skill-dir>/scripts/ledger.py add-doc --kind visit-memo --title "みなと耳鼻咽喉科 2026-09-25（金）10:30" --for "佐々木先生"
python3 <skill-dir>/scripts/ledger.py add-line --doc D0001 --type self --text "鼻づまり：「少し良くなった気がする」（9/22）" --cite "S0004:少し良くなった気がする"
python3 <skill-dir>/scripts/ledger.py add-line --doc D0001 --type guess --text "ChatGPTの推測：「副鼻腔炎かも」（未確認）" --cite "S0005:副鼻腔炎かも"
```

- **What the script refuses:** a line without a cite, a quote that isn't verbatim (only whitespace may differ), `quoted` without a quote from a non-AI source, `document` without a photo or document source, a line citing `other_ai` that isn't a `guess`, and revising a guess into a fact. Read the error, fix the command, and never work around it.
- **Promoting a guess:** do it only when the support is recorded or she confirms, and tell her:
  `promote --line L0006 --to quoted --evidence "S0007:副鼻腔炎ですね"` or `promote --line L0006 --to self --confirmed-by-her`.
- **Revising:** `revise-line --line L0002 --text "..." --reason "..."`. Pass `--actor her` when the correction is hers.
- **Timelines:** a `timeline` doc shows lines in the order they were added, so put each event's absolute date in its text.

### 3. Run `check`

```bash
python3 <skill-dir>/scripts/ledger.py check
```

Run it after each batch of changes and always before you show her a memo. It exits 1 on any error:

1. **chain:** every event links to the one before it and every hash recomputes. A failure means the log was changed outside the script. Stop writing, tell her, and restore the file from her copy if she has one. Don't try to repair the log.
2. **cites:** every line cites at least one existing source.
3. **quotes:** every quote is in its source verbatim, apart from whitespace.
4. **types:** the claim-type and promotion rules above.
5. **time:** no relative time words (今日, 昨日, 先週, 3日前, yesterday, ...) in record lines or doc titles. A source may contain them, but without a confirmed `happened_at` that is a warning: ask her, then `note --about S0001 --happened-at 2026-09-23 --confirmed --text "..."`.
6. **approval:** approvals are hers, and each is bound to the revision she saw. `check` also lists the drafts.

Fix every error with a new event and run `check` again.

### 4. Render and show

```bash
python3 <skill-dir>/scripts/ledger.py render            # kune-ledger/views/index.html, every doc
python3 <skill-dir>/scripts/ledger.py render --doc D0001 # kune-ledger/views/D0001.html
```

- **The view:** a single static HTML file that loads nothing from the network. Each line shows its type badge (推測（未確認） has a dashed border), its status, and source chips such as 「9/22 音声 0:14」. Tapping a chip shows the source verbatim, with its times and origin and the line's history. The header shows the last `check` and whether anything changed after it, so run `check` right before `render`.
- **Showing it:** give her the path (on claude.ai, the file). Don't publish it as a web page or an artifact, and don't upload it anywhere.
- **Approving:** when she has read the lines and says they are right, run `approve --line L0001` or `approve --doc D0001` (every draft line in the doc). Then run `check` and `render` again.

### Where did this come from?

When she asks where a fact came from, find the line in `state`, run `history --line L0003`, and show her the source verbatim with its time and origin (kind, file, page, media time). If nothing in the ledger supports a claim, say so plainly; don't reconstruct it from memory.

## Commands

| Command | What it does |
|---|---|
| `init [--tz Asia/Tokyo] [--profile health-visit]` | creates `ledger.json`, an empty `log.jsonl` and `views/` |
| `now [--days N] [--json]` | the clock: UTC, local time, the date and the weekday in Japanese |
| `add-source --kind K (--text T \| --stdin) [...]` | records a source verbatim → `S0001` |
| `add-doc --kind visit-memo\|record\|timeline --title T [--for W]` | starts a doc → `D0001` |
| `add-line --doc D --type T --text T --cite S0001[:quote]...` | adds a cited line → `L0001` |
| `revise-line --line L [--text] [--type] [--cite ...] --reason R` | a new revision; back to draft |
| `promote --line L --to T (--evidence S[:quote] \| --confirmed-by-her)` | turns a guess into another type |
| `approve (--line L \| --doc D)` | her approval, bound to the current revision |
| `note --text T [--about ID] [--happened-at D --confirmed]` | a note in the log; can confirm a source's date |
| `state [--json]`, `history --line L` | read the current state, or one line's events |
| `check [--json]` | all rules; exit 1 on any error |
| `render [--doc D] [--out F]` | the static HTML view |

Every write command appends exactly one event and prints the new id first. The format, every flag and the exit codes are in [references/ledger-format.md](references/ledger-format.md).

## Out of scope

- The skill gives no diagnosis, triage, department or dose instructions, and it adds no medical content to her records.
- If she asks a medical question, answer as you normally would, outside the ledger. If she wants that answer kept, store it as an `other_ai` source (`--speaker Claude`), and any line drawn from it as a `guess`.
- It has no reminders and no app. The check runs only when you run it, which is why the view says when it last passed.

## Privacy

- The ledger stays in her folder. Never copy it elsewhere: no uploads, no other folders, no repositories, no artifacts.
- Store only what she chooses to keep.
- The files hold health information. Show her the parts she asks about; don't paste the whole log into the conversation.

## References and examples

- [references/ledger-format.md](references/ledger-format.md): the folder, the event format and hash, every op and command.
- [references/claim-types.md](references/claim-types.md): codes, labels, choosing a type, promotion, profiles.
- [references/time.md](references/time.md): the clock, time zones, converting relative dates, the word list `check` uses.
- [examples/WALKTHROUGH.md](examples/WALKTHROUGH.md): a short session with the exact commands and their output.
- `examples/sample-ledger/`: a fictional sample ledger (青木 美月, an ENT story, 2026-09-16 to 2026-09-25), built by `examples/build_sample.py`.
