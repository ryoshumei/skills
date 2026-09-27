# Ledger format and commands

The ledger is generic: sources, docs, lines, claim types and an event log. The health profile only supplies labels (see [claim-types.md](claim-types.md)).

## Contents

- [The folder](#the-folder)
- [Events and the hash chain](#events-and-the-hash-chain)
- [Ops](#ops)
- [State](#state)
- [Commands](#commands)
- [What the script refuses, and what check reports](#what-the-script-refuses-and-what-check-reports)
- [The last check and the anchor](#the-last-check-and-the-anchor)
- [Platforms, encoding, the clock](#platforms-encoding-the-clock)

## The folder

```text
kune-ledger/
  ledger.json   meta, written once by init
  log.jsonl     the only authoritative store: append-only, hash-chained events
  views/        generated: check.json (the last check) and the HTML views; safe to delete
```

`ledger.json`:

```json
{
  "format": "kune-trace-ledger",
  "format_version": 1,
  "profile": "health-visit",
  "timezone": "Asia/Tokyo",
  "created_at": "2026-09-24T21:00:00+09:00",
  "sample": true
}
```

`sample` is present only in fictional sample ledgers (`init --sample`); the view then shows 「サンプルデータ」. The script writes its files owner-only where the operating system supports it, because they hold health information.

## Events and the hash chain

Each line of `log.jsonl` is one event:

```json
{"actor":"her","at":"2026-09-24T21:02:00+09:00","data":{...},"hash":"…64 hex…","op":"add_source","prev":"…64 hex…","seq":1}
```

| Field | Meaning |
|---|---|
| `seq` | 1, 2, 3, … with no gaps |
| `at` | the system clock when the event was written: ISO 8601, whole seconds, with the ledger's UTC offset |
| `actor` | `her` or `claude`: who made the change |
| `op` | one of the ops below |
| `data` | the op's payload |
| `prev` | the `hash` of the previous event; 64 zeros for event 1 |
| `hash` | `sha256_hex(prev + canonical_json({seq, at, actor, op, data}))`, over UTF-8 bytes |

**Canonical JSON** means keys sorted, no whitespace between tokens, and non-ASCII characters written as themselves. In Python that is `json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`.

Each stored line is the canonical JSON of the whole event (`prev` and `hash` included), ending with a single `\n`. The file ends with `\n` and has no blank lines. So any edit shows:

- a changed character breaks that event's hash;
- a changed hash breaks the next event's `prev`;
- a deleted or reordered line breaks `seq` and `prev`;
- even a whitespace-only edit fails, because the line is no longer canonical.

Deleting the *last* events leaves a valid shorter chain. The anchor in `views/check.json` catches that (see below).

## Ops

IDs are sequential per kind: sources `S0001`, docs `D0001`, lines `L0001`, notes `N0001`. Optional fields are left out, not stored as null.

| Op | `data` | Default actor |
|---|---|---|
| `add_source` | `{id, kind, text, speaker?, file?, page?, media_time?, happened_at?, happened_confirmed}` | her |
| `add_doc` | `{id, title, kind, for?}` | claude |
| `add_line` | `{id, doc, text, type, cites: [{source, quote?}]}` | claude |
| `revise_line` | `{line, reason, text?, type?, cites?}`: only the fields that changed; `cites` replaces the whole list | claude |
| `promote` | `{line, from: "guess", to, evidence: {source, quote?}}` or `{line, from: "guess", to, confirmed_by: "her"}`, plus `reason?` | claude (evidence), her (confirmed_by) |
| `approve` | `{lines: [{line, rev}], doc?}` | her, always |
| `note` | `{id, text, about?, happened_at?, happened_confirmed?}` | claude, or her when it confirms a date |

Source fields:

- `kind`: `chat`, `voice`, `photo`, `document`, `calendar` or `other_ai`.
- `text`: verbatim. Her words exactly, or the transcription of a photo, recording or document. Line endings are stored as `\n`; leading and trailing whitespace is dropped.
- `speaker`: who said or wrote it, when that matters (`本人`, `ChatGPT`, `Claude`).
- `file`: the photo, recording or document in her folder (a relative path, with `/`).
- `page`: a page number, from 1.
- `media_time`: the position in a recording where this text starts, as `m:ss` or `h:mm:ss`. Record a long recording as one source per part you cite, each with its own `media_time`.
- `happened_at`: when it happened, if that differs from when it was recorded. It is an absolute ISO date (`2026-09-23`) or datetime with an offset (`2026-09-22T08:15:00+09:00`). A datetime given without an offset gets the ledger's.
- `happened_confirmed`: `true` when she confirmed the date, or it is printed on the document.

Doc kinds: `visit-memo` (受診メモ), `record` (記録), `timeline` (時系列).

Line types: `quoted`, `document`, `self`, `guess`. Each cite is `{source}` or `{source, quote}`, where `quote` is a contiguous substring of the source's text after whitespace normalization.

## State

The state is rebuilt from the log on every command and never stored:

- **Source:** its `add_source` data, plus `captured_at` (the event's `at`). A `note` with `about: S…` and `happened_at` sets that source's `happened_at` and `happened_confirmed`. Nothing else about a source ever changes.
- **Line:** starts at `rev` 1 as a `draft`. Every `revise_line` or `promote` adds 1 to `rev` and sets it back to `draft`. An `approve` entry `{line, rev}` makes it `approved` only if `rev` is the line's current revision.
- **Promotion:** a `promote` with `evidence` also adds the evidence as a cite, unless the line already has it.
- **Order:** docs list their lines in the order they were added.

## Commands

`python3 <skill-dir>/scripts/ledger.py <command> [options]`. Every command takes `--dir <folder>` (default `./kune-ledger`). Write commands take `--actor her|claude` to override the default actor, except `approve`, which is always `her`.

| Command | Options | Prints |
|---|---|---|
| `init` | `--tz` (IANA name or `+09:00`; default `Asia/Tokyo`), `--profile` (default `health-visit`), `--sample` | `initialized kune-ledger (…)` |
| `now` | `--days N`, `--tz`, `--json` | UTC, local time, the date and the weekday in Japanese; `--days N` adds the local date N days away |
| `add-source` | `--kind`, `--text` or `--stdin`, `--speaker`, `--file`, `--page`, `--media-time`, `--happened-at`, `--confirmed` | `S0001  (add_source #1, <at>)` |
| `add-doc` | `--kind`, `--title`, `--for` | `D0001  (add_doc #4, <at>)` |
| `add-line` | `--doc`, `--type`, `--text`, `--cite S0001[:quote]` (repeat for more) | `L0001  (add_line #5, <at>)` |
| `revise-line` | `--line`, `--reason`, and at least one of `--text`, `--type`, `--cite` | `L0001  rev 2, draft  (revise_line #8, <at>)` |
| `promote` | `--line`, `--to`, `--evidence S0007[:quote]` or `--confirmed-by-her`, `--reason` | `L0006  guess → quoted, draft, evidence S0007  (…)` |
| `approve` | `--line L0001` or `--doc D0001` (every draft line in the doc, one event) | `L0001,L0002  approved  (approve #9, <at>)` |
| `note` | `--text`, `--about`, `--happened-at`, `--confirmed` | `N0001  (note #12, <at>)` |
| `state` | `--json` | sources, docs with their lines, notes, and the head (`#seq` and hash) |
| `history` | `--line` | every event of the line: created, revised (with reasons), promoted, approved, notes about it |
| `check` | `--json` | one line per problem, the drafts, then `result PASS` or `result FAIL` |
| `render` | `--doc`, `--out` | `wrote kune-ledger/views/index.html` |

A cite is `S0003` or `S0003:quote`. The first ASCII colon separates the id from the quote, so the quote itself may contain colons. Quote the whole argument in the shell (`--cite "S0004:少し良くなった気がする"`); that works in bash, zsh, PowerShell and cmd.

Exit codes: `0` success; `1` `check` found an error; `2` the command was refused or mistyped, with the reason on stderr after `error:`. A refused command writes nothing.

## What the script refuses, and what check reports

The write commands refuse anything that would break a core promise:

- a line with no cite, a cite to a missing source, a quote that isn't verbatim, an empty quote;
- `quoted` without a quote from a source that isn't `other_ai`;
- `document` without a photo or document source;
- a line citing `other_ai` that isn't a `guess`, and adding an `other_ai` cite to a fact;
- revising a `guess` into another type (that is `promote`'s job), and promoting a line that isn't a guess;
- `approve` by `claude`, approving a line that is already approved, a relative or impossible `--happened-at`, and a revision that changes nothing.

Relative time words in a line are *not* refused, because converting them needs her confirmation, which may take a turn. `check` reports them as errors.

`check` re-verifies everything from the log, including logs written by other means:

| Rule | Error when |
|---|---|
| 1 chain | a line isn't canonical JSON, `seq` skips, `prev` or `hash` doesn't match, the file doesn't end with `\n`, an event is malformed, or the log lost or changed an event the last check saw. A clock that runs backwards is a warning. |
| 2 cites | a line cites nothing, or cites a source that doesn't exist |
| 3 quotes | a quote isn't in its source verbatim (whitespace aside) |
| 4 types | `quoted` without a non-AI quote; `document` without a photo or document source; a guess turned into another type without `promote`; a fact citing `other_ai` without a `promote` after that cite was added; an invalid `promote` |
| 5 time | a relative time word in a line's text, a doc's title or its `for`; a `happened_at` that isn't absolute. A source whose text has one without a confirmed `happened_at` is a warning. |
| 6 approval | an `approve` written by `claude`, or one for a revision that wasn't current. Drafts are listed. |

## The last check and the anchor

`check` saves its result to `views/check.json`:

```json
{"checked_at": "…", "ok": true, "errors": 0, "warnings": 0, "drafts": ["L0006"],
 "head": {"seq": 14, "hash": "…"}, "anchor": {"seq": 14, "hash": "…"}}
```

`render` shows `checked_at` and the result in the page header. When the log has changed since (`head` differs), the header says so. The `anchor` is the newest event a check has seen with an intact chain. A failing check never lowers it, so if events are later removed from the end of the log, or rewritten, every check fails until the log is restored. Deleting `views/` resets this, and the view then shows 「チェック未実行」.

## Platforms, encoding, the clock

- **Requirements:** Python 3.9 or later, standard library only, and no network access. It runs on macOS, Windows, Linux and the claude.ai sandbox.
- **Encoding:** every file is UTF-8 with `\n` line endings. `--stdin` reads UTF-8 and drops a byte-order mark. Output is UTF-8 even on a legacy Windows console, and paths are printed with `/`.
- **One writer at a time.** Each write re-reads the log and refuses to append if the file changed while it ran, so don't run two write commands at once.
- **The clock:** the only clock is `system_now()` in `ledger.py`, which reads the system clock. No option or environment variable sets the time. The tests and `examples/build_sample.py` pin it from inside Python so their output is reproducible.
