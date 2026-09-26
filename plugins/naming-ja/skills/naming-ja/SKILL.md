---
name: naming-ja
description: "Name a product, app, feature or mascot for Japan together with the user. Capture their taste first, generate a wide list across Japanese naming styles (katakana coinages, hiragana and yamato-kotoba, kanji, wordplay, romaji), let them star and kill names, and score only the shortlist. Then check the finalists for collisions (the Japanese App Store, Google Play, J-PlatPat trademarks, domains, handles) and for bad meanings in Japanese, English and Chinese. Use whenever the user wants to name or rename something for Japanese users (命名, 起名, 取名, ネーミング, 名前を考えて, 名前案, app name, brand name), or says they don't like an earlier naming shortlist, even if they never mention a skill."
---

# Japanese naming

A good name is one the owner is glad to see on their home screen, and no rubric can stand in for that. A round that generates first and lets a judge choose tends to produce well-argued names the owner doesn't like. So this process asks for the owner's taste before generating anything and shows a wide spread early. It lets the owner make every cut and runs collision checks only on names they already like.

The structure (strategy, big list, scored shortlist, due diligence) is adapted from arn-spark-naming (AppsVortex/arness, MIT License). It has been rebuilt for Japanese scripts, Japanese registries and health products. Below, `<skill-dir>` means this skill's base directory, which Claude Code shows when the skill loads. The scripts need Node 20 or later and nothing else.

## Ground rules

- **Speak the user's language.** Show each name in Japanese with its kana reading and romaji. Explain it in the language the user writes in, for example Chinese.
- **The owner's taste decides.** Scores explain trade-offs, but they never pick the winner. A starred name survives every filter.
- **No private records.** Never open private notes (such as `*.private.md` files) or real health data, even for inspiration.
- **Add, don't overwrite.** Another session may be editing the same repo. Record results in a new dated file and never edit existing naming files. Don't commit or push unless the user asks.
- **Health products make no medical promises.** A patient-side app helps people keep and check their own information; it is not a doctor. Reject names that promise diagnosis, cure or certainty (確定, 診断, 治る, a ドクター persona), in Japanese or through a kanji's Chinese sense. For example, a Chinese reader sees 确诊 in 確. More health-product traps are listed in [references/methodology.md](references/methodology.md).

## Step 0: Context (quiet)

1. Read the product concept: `CONCEPT.md`, then `README.md`. Also read any spec that fixes brand constraints, such as a seal or icon system or what may show on a lock screen. If there is no concept, ask for three lines: what it does, who it's for, and what it promises.
2. Build the seen list. It holds every name in earlier naming work, such as `naming/*.md`, including names marked dropped, cut or considered. It also holds the existing apps and marks found as collisions.
   - Write it to a scratch file in the format `scripts/seen-check.mjs` reads: one name per line, spellings separated by `|`, then a tab and a note. Give each kanji name its kana reading.
   - A brief from an earlier run of this skill ends with a `seen` block, which the script reads directly.
   - If the earlier work spans many files, have an Explore subagent build the list.
3. Earlier files usually hold the writers' and judges' opinions, not the owner's. Don't treat them as the owner's reactions; ask in Step 1 instead. Cite checks that are already recorded instead of repeating them.
4. Note fixed constraints, such as a one-character seal (印) mark or a companion voice.

## Step 1: Taste interview (before any new name)

Generating first and asking later is how naming rounds miss. So ask first, with AskUserQuestion. Draw the options from the earlier round and the product, so the answers are concrete, and write them in the user's language. Two short rounds are usually enough. The examples below are for a patient-side health app, asked in Chinese.

Round 1 (up to four questions):

- **What went wrong last time?** (multiSelect) For example: 太直白 (too literal), 太可爱 (too cute), 太硬 (too stiff or official), 要解释才懂 (needs explaining), 像确诊或承诺 (sounds like a medical promise), 像聊天机器人 (sounds like a chatbot), 听着旧 (dated), 读起来别扭 (awkward to say).
- **Script** (multiSelect): カタカナ, ひらがな, 漢字, ローマ字.
- **Sound** (multiSelect): 2–3, 4, or 5 or more morae; soft (な・ま・や・わ行) or crisp (か・さ・た行).
- **Personality:** 付き添い (companion), 記録係 (record keeper), 相棒 (buddy), 番人 (guardian), or 道具 (a plain tool).

Round 2 (up to four questions):

- **Meaning to carry** (multiSelect): 出典 (a source for every fact), 付き添い (company before and after the visit), 控え (your own copy), 日付 (dates and times), 言葉 (the doctor's words), or none (pure sound).
- **Names they like** (multiSelect): offer pairs of well-known names that each stand for a style. Examples are Notion / Slack (a real word), メルカリ / ヤクルト (a reshaped foreign root), いろはす / ぐるなび (a blend) and たまごっち / ポケモン (a playful cut). The free-text answer lets them name their own.
- **Words they hate** (multiSelect): for example medical words, stock app suffixes (〜ナビ, 〜ノート, 〜帳, 〜AI) or cute doubled words.
- **Where the name will be used:** a demo only, a store release, or undecided. The answer sets how strict Step 5 is, and undecided means preparing for the demo while marking what a release would need.

AskUserQuestion takes four options at most, so offer the four likeliest and let the free-text answer cover the rest.

Then write a taste profile of five lines or fewer, plus the dead directions, and confirm it in one message. Answers can pull against each other, such as 太直白 and 要解释才懂. Say how you read them together, for example "a real word or a foreign root that works as pure sound, with meaning as a bonus", and confirm that too. The profile steers every later step.

## Step 2: A wide first batch

- Pick 5–8 styles from [references/methodology.md](references/methodology.md) that fit the profile. Add one wildcard, to test an assumption: 3–4 names in a style the profile didn't choose but didn't rule out. If no such style is left, skip it.
- Write 4–8 names per style, 40–60 in all, and expect the quick screen below to drop many of them. In one real run it dropped 9 of 13 short names, so draft about twice as many as you plan to show. Don't pad a style with weak names to reach a count. Give each name's reading, romaji and one-line meaning. Don't score them yet, because scores anchor the owner too early.
- Screen the batch before you show it:
  - Run the counter test and the in-context test from methodology.md. Drop names that hit an obvious health-product trap; the full checks wait for Step 5.
  - Run `node <skill-dir>/scripts/seen-check.mjs --seen <seen list> --candidates <batch file>`. It flags names that repeat or nearly repeat a seen name, and near-twins inside the batch. Judge each flag: drop the name, rework it, or keep it and say why.
  - Quick-screen for collisions: `node <skill-dir>/scripts/check-names.mjs --tm --quick "カナ|romaji" …`. It takes about 7 seconds a name, so run it in the background while you lay out the tables. Drop names with an exact App Store match in a related genre, or a same-reading mark in the relevant classes, and say how many you dropped. Short, soft names are the ones most often taken, and a batch that skips this step lets the owner fall for names they can't have.
- Show the names grouped by style, in compact tables, with little text around them. Ask the owner to mark ⭐ on anything they like even a little, ✗ on any style to drop, and "more like X" where they want more. Their reactions are the data, so don't argue with them.

## Step 3: Deepen around the stars

- Ask what they like about each star: the sound, the meaning or the look. The answer tells you which of those to keep and which to vary. In one run the owner liked one star for its sound and another for its meaning, and that steered every later batch.
- Vary the starred names: other scripts (アサヒ, あさひ, ASAHI), one mora more or less, other endings, blends of starred pieces, and neighbouring meanings.
- Keep the form of what they star. If they star short real words, look for more short real words, in other languages or other senses. Longer coinages and blends usually answer a different taste, even when they keep the meaning.
- For more volume, run one subagent per starred direction. Give each one the taste profile, the dead directions and the seen list. When separate generators land on the same name, someone else has usually taken it already, so check that name first.
- Run seen-check.mjs and the quick screen on each new batch, with the earlier batches added to the seen list.
- If a batch gets no star, or only one, ask one short question about what was wrong before writing the next batch: too long, a made-up word, the sound, or the meaning. Guessing costs a whole round.
- Check in with the owner again. Repeat until they have 3–8 names they would be happy to see on their phone.

## Step 4: Score the shortlist (advisory)

Score each shortlisted name from 1 to 5 on the six lenses (六感) in [references/methodology.md](references/methodology.md). Put the owner's ⭐ count in its own column and never add it to the score. Give one line of trade-offs per name. The owner picks 3–6 finalists to check.

## Step 5: Collision and meaning checks (finalists only)

Follow [references/due-diligence.md](references/due-diligence.md):

1. Run the full scripted check on every spelling of every finalist:
   `node <skill-dir>/scripts/check-names.mjs --tm "ミナモ|みなも|水面|minamo" "…"`
   - Every spelling means katakana, hiragana, the source word in kanji if the name comes from one (水面 for ミナモ), and each plausible romaji (soeru and soel, komitari and comitari).
   - It searches the Japanese App Store (iPad-only apps too), reads same-reading trademarks from patent-i.com, asks RDAP about domains, and prints the links for the manual checks.
   - It takes about 25 seconds per name with four spellings, so run five or more finalists in the background.
   - If its requests fail behind a proxy, rerun it with `NODE_USE_ENV_PROXY=1` (Node 22.21 or later).
2. Search the web for existing brands and marks. Web search alone misses most collisions, and text-matching registers such as TMview miss look-alike readings. So also walk the owner through the J-PlatPat reading (称呼) search, which can't be automated.
3. Screen each name's meaning in Japanese, English and Chinese, and screen it against the health-product traps.

Label each finalist **Clean**, **Caution**, **Blocked** or **Unverified**. Give evidence for each label: a URL, a registration number, or an app's name with its seller and release date. A check nobody ran is Unverified, not Clean.

Judge against the use from Step 1. For a demo that never ships, a conflict found only in the trademark register is a Caution with a rename trigger. For a store release, the same conflict is Blocked. A same-name app in a related genre confuses people either way.

## Step 6: Decide and record

- The owner chooses. Offer a tagline that carries what the name leaves out, such as 付き添い when the name is about sources.
- Write the results to `naming/brief-YYYY-MM-DD.md` as a new file. If that name is taken, add `-2`. Include the taste profile, the dead directions, every candidate by style with its ⭐ and ✗ marks, the shortlist scores, the checks with evidence, and the decision.
- End the brief with a fenced block whose info string is `seen`. List every name shown this round, one per line: spellings separated by `|`, a tab, then the owner's mark (⭐, ✗ or –) and any collision found. Also list the names the quick screen dropped, with why, so the next round skips them without checking again. The next round's Step 0 and seen-check.mjs read the block as it is.
- If the chosen name is only cleared for a demo, write down in the brief what would trigger a rename, such as a store release or a clash found in J-PlatPat.
- Tell the owner the path. Commit only if they ask.
