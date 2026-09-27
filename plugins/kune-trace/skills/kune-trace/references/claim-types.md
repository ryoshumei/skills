# Claim types

Every line of a record says what kind of claim it is. The ledger stores a code, and a profile gives it a label. The type answers one question, **where did these words come from?**, not how likely they are to be true.

## Codes and the health-visit labels

| Code | Label | Meaning | Enforced, beyond "cites at least one source" |
|---|---|---|---|
| `quoted` | 医師の言葉 | another person's words, quoted verbatim from a source: in this profile, the doctor's words as she recorded them | a cite with a verbatim quote, from a source that isn't `other_ai` |
| `document` | 書類 | written on a document: a prescription, a 薬の説明書 (薬情), a test result, a referral letter | a cite to a `photo` or `document` source |
| `self` | 本人 | her own report: what she felt, noticed, did or wants to ask (cite her own words) | no `other_ai` cite without a `promote` |
| `guess` | 推測（未確認） | unconfirmed, whether it is her guess or an AI's (cite where the guess was made) | nothing more: any source may back a guess |

In the view, 推測（未確認） has a dashed badge and a dashed border, so a guess never looks like the other lines.

## Choosing a type

Take examples from the ENT sample (`examples/sample-ledger/`):

- She recorded after the visit: 「副鼻腔炎かもしれないって。アレルギー性鼻炎もあるって」. The line 「前回（9/18）の先生の言葉：「副鼻腔炎かもしれない」」 is `quoted`, citing that recording with the quote. The doctor's own hedge stays in the words: `quoted` means *the doctor said this*, not *this is certain*.
- The 薬情 photo says 「カルボシステイン錠500mg「JG」　1回1錠　1日3回　毎食後」. The line with that dose is `document`, citing the photo. If she only *said* the dose, it is `self`, until a photo or document backs it.
- Her voice memo says 「鼻づまりは少し良くなった気がする」. The line is `self`. Keep her hedge (気がする) and her degree (少し) in the line; a doctor reads 「かなり改善」 very differently.
- ChatGPT said 「副鼻腔炎かも」. She wants it kept, so it becomes a source of kind `other_ai`, and the line is `guess`. The same goes for Claude's own answers: store them as `other_ai` (`--speaker Claude`) and cite them only from guess lines.
- She says 「親知らずかも」 about her own tooth. That is her guess, so the line is `guess`, citing her message.

When in doubt between two types, pick the weaker one (`self` over `quoted`, `guess` over `self`). A later `promote` can move it up with evidence, but a line that claims too much misleads the reader in the meantime.

## Rules the script enforces

`add-line`, `revise-line` and `promote` refuse, and `check` (rule 4) reports:

1. `quoted` without at least one cite with a verbatim quote from a source that isn't `other_ai`. An AI's words are never 医師の言葉.
2. `document` without a cite to a `photo` or `document` source.
3. A line that was a `guess` and is now another type without a `promote` event. `revise-line` can't do it, and it tells you to use `promote`.
4. A line citing an `other_ai` source that is `quoted`, `document` or `self` without a `promote` after that cite was added. A new line that cites `other_ai` must start as `guess`, and a fact can't gain an `other_ai` cite by revision.

Changing a fact into a `guess` (demoting it) is always allowed with `revise-line`, and a reason. Moving it back needs a new `promote`.

## Promotion

A guess becomes another type only through `promote`, which needs exactly one basis, and the log keeps which:

- **Evidence:** a source that supports it, with a quote when the target type needs one.
  `promote --line L0006 --to quoted --evidence "S0007:副鼻腔炎ですね"`
  The event stores `evidence: {source, quote}`, and the evidence is added to the line's cites. Use it when the support is recorded: the doctor said it (a later debrief), or a document shows it.
- **Her confirmation:** `promote --line L0006 --to self --confirmed-by-her`
  The event stores `confirmed_by: "her"` and is written as her. Use it only after she says so explicitly, in her own words. Her confirmation can make a guess her own report (`self`). It can't make it 医師の言葉 or 書類, because those need a quote from a non-AI source or a photo or document; record that source first, then promote with `--evidence`.

A promotion is a change, so the line goes back to draft and needs her approval again. Tell her when you promote a line and on what basis. Usually you'll also `revise-line` the text afterwards, for example from 「ChatGPTの推測：「副鼻腔炎かも」」 to 「9/25の先生の言葉：「副鼻腔炎ですね」」.

## Type and status are separate

Every line also has a status, 下書き (`draft`) or 承認済み (`approved`). The type says where the words came from, and the status says whether she has approved this exact text. She can approve a guess line, meaning "keep it as a guess". Approval never changes the type.

## Profiles

The engine only knows the four codes. A profile names them for one kind of record, and it lives in the `PROFILES` table in `scripts/ledger.py`:

```python
"health-visit": {
    "types": {"quoted": "医師の言葉", "document": "書類", "self": "本人", "guess": "推測（未確認）"},
    "type_help": {...},     # one line per type, shown under 「種類の見かた」 in the view
    "doc_kinds": {"visit-memo": "受診メモ", "record": "記録", "timeline": "時系列"},
    "source_kinds": {"chat": "チャット", "voice": "音声", "photo": "写真", "document": "文書",
                     "calendar": "カレンダー", "other_ai": "AIの回答"},
}
```

Another domain would add a profile with its own labels (for `quoted`, say, 「相手の言葉」 in place of 医師の言葉) and pass `init --profile <name>`. The codes, the rules and the log format stay the same, so the checks don't change. A ledger's profile is fixed when it is created.
