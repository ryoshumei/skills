# kune-trace (draft)

An Agent Skill, packaged as a Claude Code plugin, that keeps traceable records built from conversations. Every line of a record or visit memo (受診メモ) cites where it came from, carries a claim type, and has its time from the clock. Every change goes into an append-only, hash-chained log. The first profile is for health visits. The skill gives no medical guidance.

**Status:** draft, version 0.0.1. It is not listed in this repo's marketplace (`.claude-plugin/marketplace.json`) or its root README; the owner decides when it is. `kune-trace` is a working name, and it will be renamed along with KUNE before any public release.

## Why

People already keep their health in long chats with an AI, and three things go wrong:

- **Facts get scattered.** Weeks later, nobody can find where a fact first came from.
- **Guesses turn into facts.** "It might be sinusitis" from another AI, repeated a few times, starts to read like a diagnosis.
- **Dates drift.** 「昨日」 said on Tuesday and read on Friday, a weekday that doesn't match its date, an appointment nobody booked.

## What it does

- **A source ledger.** Every message, voice note, photo of a prescription or 薬の説明書, and quoted doctor's word she shares becomes a source with its own id. It is stored verbatim, with the time taken from the system clock.
- **Records that cite.** Every line of a record, 受診メモ or timeline cites source ids, with verbatim quotes where the wording matters. Each line has one claim type: 医師の言葉 (the doctor's words), 書類 (written on a document), 本人 (her own report) or 推測（未確認） (a guess).
- **Guesses never become facts on their own.** Answers from other AIs, and Claude's own, are stored as AI answers, and any line that cites one is a guess. Changing a guess into a fact takes a recorded source or her explicit confirmation, and the log keeps which.
- **Absolute dates.** Relative dates such as 「昨日」 are converted from the clock and confirmed with her. Her own words stay verbatim in the source.
- **An append-only log.** Every change is a new event: who made it, when, why, and whether she approved it. The events are hash-chained, so an edit to the history shows.
- **A check.** It fails when a line has no source, a quote isn't verbatim, a relative date slipped into a record, a guess changed type without a promotion, an approval doesn't match, or the chain is broken.
- **A view.** One static HTML page, readable on a phone in light and dark mode. Each line shows its type and source chips; tapping a chip shows the source verbatim, with its time and origin, and the line's history.

See [`skills/kune-trace/examples/WALKTHROUGH.md`](skills/kune-trace/examples/WALKTHROUGH.md) for a short session, and [`skills/kune-trace/examples/sample-ledger/`](skills/kune-trace/examples/sample-ledger/) for a fictional sample ledger with its rendered view (`views/index.html`).

## Where it runs and how to install it

All it needs is Python 3.9 or later: one script, `scripts/ledger.py`, using the standard library only, with no network access. It runs on macOS, Windows and Linux, and in the claude.ai code-execution sandbox.

### Claude desktop (the first target)

1. Zip the skill folder, so that the zip holds `kune-trace/SKILL.md`:
   `cd plugins/kune-trace/skills && zip -r kune-trace.zip kune-trace -x '*/__pycache__/*'`
2. In Claude, open **Customize > Skills**, click **+**, then **Create skill > Upload a skill**, and choose the zip. Code execution has to be on (**Settings > Capabilities**). These steps are from the [help center](https://support.claude.com/en/articles/12512180-use-skills-in-claude), checked 2026-09-27.
3. Open a folder on her computer as the project. The ledger is created there as `kune-ledger/`, and the files stay on that computer. On first use, Claude runs `init` and asks her to confirm that `kune-ledger/ledger.json` appeared. Writing to the folder should work, but the help center doesn't say so explicitly.

### Claude Code

It isn't in the `ryoshumei` marketplace yet. Until it is, use one of these:

- **For one session,** from a clone of this repo: `claude --plugin-dir plugins/kune-trace`
- **Copy the skill** into your skills folder: `cp -r plugins/kune-trace/skills/kune-trace ~/.claude/skills/` for every project, or into `<project>/.claude/skills/` for one project.
- **Once it is listed:** `claude plugin install kune-trace@ryoshumei`

The ledger is `kune-ledger/` in the working directory. If that directory is a Git repository, add `kune-ledger/` to `.gitignore`.

### claude.ai

1. Upload the same zip under **Customize > Skills**, with code execution on.
2. Keep her ledger in a Project by adding `ledger.json` and `log.jsonl` as project files.
3. Only she can add files to a Project. Claude works on copies in its sandbox, and after every change it gives her the updated files and tells her which ones to replace in the Project.

## Privacy

- **Where the ledger lives.** The ledger files stay in her folder. The skill never sends them anywhere, and its scripts make no network calls. On claude.ai, her folder is the Project, whose files are stored with her Claude account.
- **What Claude still sees.** The conversation itself is processed by Claude like any other conversation: keeping the files local doesn't change that, and skills are not covered by zero data retention.
- **The view.** It is a local file. A Content-Security-Policy blocks every network load, and the skill tells Claude never to publish it as a web page or artifact.
- **Her choice.** She chooses what goes in. Claude asks before recording anything she didn't clearly ask to keep.
- **Sample data.** The sample (青木 美月, an ENT story from 2026-09-16 to 2026-09-25) is fictional.

## What it doesn't do

- **No medical guidance.** It gives no diagnosis, triage, department or dose instructions, and it adds no medical content to her records. When she asks a medical question, Claude answers as it normally would, outside the ledger. If she wants that answer kept, it is stored as an AI answer, so any line from it is a guess.
- **One safety line.** If something she says may be an emergency, Claude responds to her safety first, as it normally would, and records it afterwards. It never files an emergency away silently.
- **No app features.** It has no reminders, no sync and no sharing with clinics. The check runs only when Claude runs it, so the view says when it last passed and whether anything changed since.
- **Not a medical device.** It keeps her own records in order. It doesn't replace her documents or her doctor's records.

## Layout

```text
plugins/kune-trace/
  .claude-plugin/plugin.json
  README.md
  skills/kune-trace/
    SKILL.md
    references/   ledger-format.md, claim-types.md, time.md
    scripts/      ledger.py (the CLI), ledger_view.py (the HTML for render)
    examples/     WALKTHROUGH.md, build_sample.py, sample-ledger/
    tests/        the unittest suite
```

## Development

```bash
python3 -m unittest discover -s plugins/kune-trace/skills/kune-trace/tests    # the tests
python3 plugins/kune-trace/skills/kune-trace/examples/build_sample.py         # rebuild the sample ledger
```

The tests cover the chain and tamper detection, verbatim quotes, relative-time detection, promotion, approval resets, AI answers, the clock and its fallback, the render's lack of network loads, the sample ledger, and a replay of the walkthrough.

Running `check` or `render` on `examples/sample-ledger` rewrites files in its `views/` with the real clock. `build_sample.py` puts them back, and the tests say so when the sample no longer matches a fresh build.

## Before a public release

- Rename it together with KUNE.
- Ask Anthropic whether its usage-policy review rule applies to a skill that only organizes her own records.
- Test how reliably the skill's description triggers on real prompts.

## License

MIT, see [LICENSE](../../LICENSE).
