#!/usr/bin/env node
/**
 * seen-check.mjs: flags candidate names that repeat or nearly repeat names already seen.
 *
 *   node scripts/seen-check.mjs --seen seen.txt "ソエル|そえる|soeru" "ミナモ|水面|minamo"
 *   node scripts/seen-check.mjs --seen naming/brief-YYYY-MM-DD.md --candidates batch.txt
 *
 * Seen and candidate lists hold one name per line: spellings separated by "|", the first being the
 * display name, then an optional tab and a note (where it came from, the owner's mark, a collision).
 * Lines starting with # are skipped. In a Markdown file only the lines inside ```seen fences count,
 * which is how Step 6 of the skill records each round.
 *
 * A candidate is flagged when any of its spellings, compared with any spelling of a seen name, is:
 *   same            the same after folding width, case and katakana to hiragana (アサヒ = あさひ)
 *   contains        one inside the other (3+ kana, or 4+ other characters)
 *   one mora apart  one mora added, removed, changed or swapped, both names 3+ morae (サクラ ~ サクマ)
 *   sound-alike     same number of morae (3+), same vowels, same consonants in another order (タマキ ~ タカミ)
 * The two sound rules read kana spellings only, so give every name its kana reading.
 * Candidates are also checked against each other. Flags are for a person to judge, not verdicts.
 * Exit code 0; 2 for a usage error. Zero dependencies, Node >= 20.
 */
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { fold } from './check-names.mjs';

const SMALL = new Set([...'ぁぃぅぇぉゃゅょゎ']);
const VOWEL = {};
for (const [v, chars] of Object.entries({
  a: 'あかさたなはまやらわがざだばぱぁゃゎ',
  i: 'いきしちにひみりゐぎじぢびぴぃ',
  u: 'うくすつぬふむゆるぐずづぶぷゔぅゅ',
  e: 'えけせてねへめれゑげぜでべぺぇ',
  o: 'おこそとのほもよろをごぞどぼぽぉょ',
})) for (const c of chars) VOWEL[c] = v;

const CONSONANT = {};
for (const [k, chars] of Object.entries({
  '': 'あいうえおぁぃぅぇぉ', k: 'かきくけこ', s: 'さしすせそ', t: 'たちつてと', n: 'なにぬねの',
  h: 'はひふへほ', m: 'まみむめも', y: 'やゆよゃゅょ', r: 'らりるれろ', w: 'わゐゑをゎ',
  g: 'がぎぐげご', z: 'ざじずぜぞ', d: 'だぢづでど', b: 'ばびぶべぼ', p: 'ぱぴぷぺぽ', v: 'ゔ',
})) for (const c of chars) CONSONANT[c] = k;

const isKana = (s) => s.length > 0 && /^[ぁ-ゖー]+$/.test(s);

/** Split folded hiragana into morae: small kana join the one before; っ, ん and ー stand alone. */
export function morae(s) {
  const out = [];
  for (const c of s) {
    if (SMALL.has(c) && out.length && !/[っんー]$/.test(out[out.length - 1])) out[out.length - 1] += c;
    else out.push(c);
  }
  return out;
}

/** Vowel pattern: ん is n, っ is q, ー repeats the vowel before it. */
export function vowels(ms) {
  const out = [];
  for (const m of ms) {
    if (m === 'ん') out.push('n');
    else if (m === 'っ') out.push('q');
    else if (m === 'ー') out.push(out[out.length - 1] ?? '-');
    else out.push(VOWEL[m[m.length - 1]] ?? '?');
  }
  return out.join('');
}

/** Consonant of each mora: きゃ is ky, ん is N, っ is Q, ー is L. */
export function consonants(ms) {
  return ms.map((m) => {
    if (m === 'ん') return 'N';
    if (m === 'っ') return 'Q';
    if (m === 'ー') return 'L';
    const head = CONSONANT[m[0]] ?? '?';
    return /[ゃゅょ]$/.test(m) && m.length > 1 ? `${head}y` : head;
  });
}

/** Edit distance over morae, counting a swap of neighbours as one edit. */
function distance(a, b) {
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j += 1) d[0][j] = j;
  for (let i = 1; i <= a.length; i += 1) {
    for (let j = 1; j <= b.length; j += 1) {
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
  }
  return d[a.length][b.length];
}

/**
 * Whether short occurs inside long at a syllable boundary. Kana are syllables already. In romaji a
 * match must start the word or follow a vowel, n or a doubled consonant, so "mochiyori" doesn't
 * contain "hiyori" (the h belongs to "chi"), while "fumitomo" contains "fumi".
 */
function containsAtSyllable(long, short) {
  for (let at = long.indexOf(short); at >= 0; at = long.indexOf(short, at + 1)) {
    if (isKana(short) || at === 0 || /[aeioun]/.test(long[at - 1]) || long[at - 1] === short[0]) return true;
  }
  return false;
}

/** Why two spellings count as a repeat, or null. */
export function compare(x, y) {
  const a = fold(x);
  const b = fold(y);
  if (!a || !b) return null;
  if (a === b) return 'same';
  const [short, long] = a.length <= b.length ? [a, b] : [b, a];
  if ([...short].length >= (isKana(short) ? 3 : 4) && containsAtSyllable(long, short)) return 'contains';
  if (!isKana(a) || !isKana(b)) return null;
  const ma = morae(a);
  const mb = morae(b);
  if (Math.min(ma.length, mb.length) >= 3 && distance(ma, mb) === 1) return 'one mora apart';
  const sameConsonants = () => consonants(ma).sort().join() === consonants(mb).sort().join();
  if (ma.length === mb.length && ma.length >= 3 && vowels(ma) === vowels(mb) && sameConsonants()) {
    return `sound-alike (vowels ${vowels(ma)})`;
  }
  return null;
}

/** Parse a list file: one name per line, or only ```seen fences in Markdown. */
export function parseList(text, isMarkdown) {
  let lines = String(text).split('\n');
  if (isMarkdown) {
    const fenced = [];
    let inside = false;
    for (const line of lines) {
      if (/^```seen\s*$/.test(line.trim())) inside = true;
      else if (inside && line.trim().startsWith('```')) inside = false;
      else if (inside) fenced.push(line);
    }
    lines = fenced;
  }
  return lines
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#'))
    .map((l) => {
      const [names, ...note] = l.split('\t');
      const spellings = [...new Set(names.split('|').map((s) => s.trim()).filter(Boolean))];
      return { name: spellings[0], spellings, note: note.join(' ').trim() };
    })
    .filter((e) => e.name);
}

function matches(c, entries) {
  const hits = [];
  for (const e of entries) {
    if (e === c) continue;
    const why = new Map(); // one line per reason and folded pair, so アサヒ and あさひ don't repeat it
    for (const x of c.spellings) for (const y of e.spellings) {
      const w = compare(x, y);
      const key = `${w}|${fold(x)}|${fold(y)}`;
      if (w && !why.has(key)) why.set(key, `${w}: ${x} ~ ${y}`);
    }
    if (why.size) hits.push({ entry: e, why: [...why.values()] });
  }
  return hits;
}

function usage(message) {
  if (message) console.error(message);
  console.error('usage: seen-check.mjs --seen <file> [--seen <file>…] [--candidates <file>] ["カナ|かな|romaji" …]');
  process.exit(2);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const seen = [];
  const candidates = [];
  const argv = process.argv.slice(2);
  const load = (file) => parseList(readFileSync(file, 'utf8'), /\.md$/i.test(file));
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--seen' || a === '--candidates') {
      const file = argv[++i];
      if (!file) usage(`${a} needs a file`);
      (a === '--seen' ? seen : candidates).push(...load(file));
    } else if (a.startsWith('--')) usage(`unknown option: ${a}`);
    else candidates.push(...parseList(a.replace(/\t/g, ' '), false));
  }
  if (!seen.length || !candidates.length) usage('need a seen list and at least one candidate');

  let flagged = 0;
  const out = [];
  for (const c of candidates) {
    const seenHits = matches(c, seen);
    const batchHits = matches(c, candidates);
    if (seenHits.length) flagged += 1;
    out.push(`${seenHits.length ? 'SEEN ' : batchHits.length ? 'BATCH' : 'ok   '} ${c.spellings.join(' · ')}`);
    for (const h of seenHits) out.push(`      seen:  ${h.why.join('; ')}${h.entry.note ? `  [${h.entry.note}]` : ''}`);
    for (const h of batchHits) out.push(`      batch: ${h.why.join('; ')}`);
  }
  out.push('', `${candidates.length} candidates checked against ${seen.length} seen names; ${flagged} repeat or nearly repeat one.`);
  console.log(out.join('\n'));
}
