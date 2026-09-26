#!/usr/bin/env node
/**
 * check-names.mjs: a first-pass collision check for candidate app names in Japan.
 *
 *   node scripts/check-names.mjs "アサヒ|あさひ|ASAHI" "みなも|ミナモ|水面|minamo"
 *   node scripts/check-names.mjs --tlds com,app,ai --max-contains 30 --json "…"
 *   node scripts/check-names.mjs --tm --quick "ソエル|SOELU" "ミナモ|minamo"  # pre-screen a batch
 *
 * Each argument is one candidate: its spellings separated by "|", the first being the display name.
 *   - App Store (Japan): searches every spelling with the iTunes Search API, once for iPhone and
 *     universal apps and once for iPad-only apps, and lists the apps whose name contains it.
 *     Apple's search is fuzzy and literal about script (a katakana search misses an app named in
 *     Latin letters), so pass every
 *     spelling. Matching folds width, case and katakana to hiragana, so アサヒ matches あさひ.
 *     "exact" is the title's name part; "exact (reading)" is a reading in parentheses, as in
 *     「SOELU(ソエル)」, which is as serious a collision.
 *   - Domains: for each ASCII spelling, asks the TLD's RDAP server (found through IANA's bootstrap
 *     file) whether <spelling>.<tld> is registered: 200 is registered, 404 is not. Anything else,
 *     including 429 and a TLD without RDAP (.jp, .io), is unknown, never "available".
 *   - Trademarks (--tm): for each kana spelling, reads the first page (10 newest) of patent-i.com's
 *     list of Japanese marks with that
 *     exact reading (JPO data, a secondary source; its robots.txt allows this at 5 s intervals) and
 *     lists the marks in the classes that matter (--classes, default 9,42,44). Similar readings and
 *     the final say still need J-PlatPat's 称呼(類似検索).
 *   - Links for the checks a script must not or cannot do: Google Play (its robots.txt disallows
 *     search), J-PlatPat (bans automated access), JPRS WHOIS for .jp, X and Instagram.
 *
 * A hit is a finding, not a failure: the exit code is 0, or 2 for a usage error.
 * Zero dependencies, Node >= 20. Apple allows about 20 searches a minute and sometimes answers 403
 * anyway, so calls are spaced 3.2 s apart and retried twice with a longer wait.
 */
import { setTimeout as sleep } from 'node:timers/promises';
import { pathToFileURL } from 'node:url';

const ITUNES = 'https://itunes.apple.com/search';
const BOOTSTRAP = 'https://data.iana.org/rdap/dns.json';
const J_PLATPAT = 'https://www.j-platpat.inpit.go.jp/t0100';
const GAP_MS = 3200;
const RETRY_MS = [8000, 20000];
const TIMEOUT_MS = 15000;
const DEFAULT_TLDS = ['com', 'app'];
const DEFAULT_MAX_CONTAINS = 12;
const PATENT_I = 'https://patent-i.com/tm/pron/';
const TM_GAP_MS = 5000; // patent-i.com's robots.txt asks for a 5 s crawl delay
const DEFAULT_CLASSES = [9, 42, 44];
const RANK = { exact: 0, 'exact (reading)': 1, contains: 2 };

/** The comparison form: NFKC, lower case, katakana to hiragana, no spaces, punctuation or symbols (ー stays). */
export function fold(s) {
  return String(s ?? '')
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[ァ-ヶ]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0x60))
    .replace(/[\s\p{P}\p{S}]/gu, '');
}

/** An app title's name part: before a subtitle ("SOELU - …", "Fio—Joanna Soh …", "Brusher: …", "アサヒ｜…"), minus a trailing reading ("綾鷹（あやたか）"). */
export function head(title) {
  return String(title ?? '')
    .split(/\s+[-–—|]\s+|[–—]|:\s|[｜：【「\[]/)[0]
    .replace(/\s*[（(][^（）()]*[）)]\s*$/, '')
    .trim();
}

/** Readings an app title gives in parentheses: 「SOELU(ソエル)」 gives ソエル. */
export function readings(title) {
  return [...String(title ?? '').matchAll(/[（(]([^（）()]+)[）)]/g)].map((m) => m[1]);
}

/** A spelling usable as a domain label or handle, or null. */
function asciiLabel(s) {
  const t = s.toLowerCase();
  return /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(t) ? t : null;
}


function usage(message) {
  if (message) console.error(message);
  console.error('usage: check-names.mjs [--tm] [--classes 9,42,44] [--quick] [--tlds com,app] [--max-contains 12] [--json] "カナ|かな|romaji" …');
  process.exit(2);
}

let lastItunesCall = 0;
async function itunes(term, entity) {
  const query = new URLSearchParams({ term, country: 'jp', entity, limit: '200' });
  for (let attempt = 0; ; attempt += 1) {
    const wait = lastItunesCall + GAP_MS - Date.now();
    if (wait > 0) await sleep(wait);
    lastItunesCall = Date.now();
    let status;
    try {
      const res = await fetch(`${ITUNES}?${query}`, { signal: AbortSignal.timeout(TIMEOUT_MS) });
      if (res.ok) return (await res.json()).results ?? [];
      status = `HTTP ${res.status}`;
    } catch (e) {
      status = e.cause?.code ?? e.message;
    }
    if (attempt >= RETRY_MS.length) throw new Error(status);
    console.error(`  ${status}; retrying in ${RETRY_MS[attempt] / 1000} s`);
    await sleep(RETRY_MS[attempt]);
  }
}

let bootstrap;
async function rdapBase(tld) {
  bootstrap ??= fetch(BOOTSTRAP, { signal: AbortSignal.timeout(TIMEOUT_MS) }).then((r) => {
    if (!r.ok) throw new Error(`IANA bootstrap HTTP ${r.status}`);
    return r.json();
  });
  const { services = [] } = await bootstrap;
  const service = services.find(([tlds]) => tlds.includes(tld));
  if (!service) return null;
  const urls = service[1];
  return urls.find((u) => u.startsWith('https://')) ?? urls[0];
}

async function domain(label, tld) {
  const name = `${label}.${tld}`;
  try {
    const base = await rdapBase(tld);
    if (!base) return { domain: name, status: 'unknown (no RDAP for this TLD; check by hand)' };
    const res = await fetch(`${base.replace(/\/?$/, '/')}domain/${name}`, {
      headers: { accept: 'application/rdap+json' },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    const status = res.status === 200 ? 'registered' : res.status === 404 ? 'not registered' : `unknown (HTTP ${res.status})`;
    return { domain: name, status };
  } catch (e) {
    return { domain: name, status: `unknown (${e.cause?.code ?? e.message})` };
  }
}

function manualLinks(spellings) {
  const enc = encodeURIComponent;
  const labels = [...new Set(spellings.map(asciiLabel).filter(Boolean))];
  const terms = [...new Set(spellings.map((s) => s.normalize('NFKC')))];
  return {
    googlePlay: spellings.map((s) => `https://play.google.com/store/search?q=${enc(s)}&c=apps&hl=ja&gl=JP`),
    jPlatPat: J_PLATPAT,
    jPlatPatQuick: terms.map((s) => `https://www.j-platpat.inpit.go.jp/?uri=/s0100/41${encodeURI(s)}/ja`),
    jprs: labels.map((l) => `https://whois.jprs.jp/?type=DOM&key=${enc(`${l}.jp`)}`),
    x: labels.map((h) => `https://x.com/${h}`),
    instagram: labels.map((h) => `https://www.instagram.com/${h}/`),
  };
}

const toKatakana = (s) => s.normalize('NFKC').replace(/[ぁ-ゖ]/g, (c) => String.fromCharCode(c.charCodeAt(0) + 0x60));
const isKana = (s) => /^[ぁ-ゖァ-ヺー]+$/.test(s.normalize('NFKC'));

async function appStoreFor(spellings, quick, tag) {
  const apps = new Map();
  const errors = [];
  for (const term of spellings) {
    for (const entity of quick ? ['software'] : ['software', 'iPadSoftware']) {
      console.error(`${tag} App Store (JP, ${entity}): ${term}`);
      let results;
      try {
        results = await itunes(term, entity);
      } catch (e) {
        errors.push(`App Store (${entity}) for ${term}: ${e.message}`);
        continue;
      }
      const key = fold(term);
      for (const r of results) {
        if (!key || !fold(r.trackName).includes(key)) continue;
        const match = fold(head(r.trackName)) === key ? 'exact'
          : readings(r.trackName).some((t) => fold(t) === key) ? 'exact (reading)' : 'contains';
        const seen = apps.get(r.trackId);
        if (seen) {
          if (entity === 'software') seen.iPadOnly = false;
          if (RANK[match] < RANK[seen.match]) Object.assign(seen, { match, term });
          continue;
        }
        apps.set(r.trackId, {
          match,
          app: r.trackName,
          seller: r.sellerName ?? r.artistName ?? '',
          genre: r.primaryGenreName ?? '',
          released: String(r.releaseDate ?? '').slice(0, 10),
          iPadOnly: entity === 'iPadSoftware',
          url: r.trackViewUrl ?? '',
          trackId: r.trackId,
          term,
        });
      }
    }
  }
  if (quick) errors.push('iPad-only apps (skipped by --quick)');
  return { appStore: [...apps.values()].sort((a, b) => RANK[a.match] - RANK[b.match]), errors };
}

/** Parse one patent-i.com reading page: the total, the JPO update date and the listed marks. */
export function parseTmPage(html) {
  const total = Number((html.match(/特許庁発行の(\d+)件/) ?? [])[1] ?? NaN);
  const updated = (html.match(/最終更新日：<time datetime="(\d{4}-\d{2}-\d{2})/) ?? [])[1] ?? '';
  const start = html.indexOf('t-vertical');
  const rows = [];
  if (start >= 0) {
    for (const tr of html.slice(start, html.indexOf('</table>', start)).split('<tr').slice(1)) {
      const num = tr.match(/href="(\/tm\/record\/[^"]+)">\s*(登録|出願)\s*([0-9-]+)/);
      if (!num) continue;
      const field = (label) => (tr.match(new RegExp(`${label}</small>\\s*([^<]+)`)) ?? [])[1]?.trim() ?? '';
      rows.push({
        number: `${num[2]}${num[3]}`,
        mark: field('文字商標'),
        holder: field('商標権者・商標出願人'),
        classes: [...field('商標区分').normalize('NFKC').matchAll(/\d+/g)].map(Number),
        readings: field('称呼\\(呼称\\)・ネーミング'),
        filed: (tr.match(/<small>出願<\/small>\s*([\d-]+)/) ?? [])[1] ?? '',
        registered: (tr.match(/<small>登録<\/small>\s*([\d-]+)/) ?? [])[1] ?? '',
        url: `https://patent-i.com${num[1]}`,
      });
    }
  }
  return { total, updated, rows };
}

let lastTmCall = 0;
/**
 * Marks with each kana spelling's exact reading, from the first page of patent-i.com's list (its 10
 * newest marks). The site's later pages don't load without a browser, so a longer list is reported
 * as partly unread, which the caller must treat as Unverified.
 */
async function trademarksFor(spellings, classes, tag) {
  const out = [];
  const errors = [];
  for (const reading of [...new Set(spellings.filter(isKana).map(toKatakana))]) {
    const url = `${PATENT_I}${encodeURIComponent(reading)}/`;
    const found = { reading, url, total: NaN, updated: '', marks: [], relevant: [] };
    try {
      const wait = lastTmCall + TM_GAP_MS - Date.now();
      if (wait > 0) await sleep(wait);
      lastTmCall = Date.now();
      console.error(`${tag} trademarks (patent-i.com): ${reading}`);
      const res = await fetch(url, {
        headers: { 'user-agent': 'naming-ja check-names (Claude Code skill)' },
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const parsed = parseTmPage(await res.text());
      const unique = [...new Map(parsed.rows.map((m) => [m.number, m])).values()];
      Object.assign(found, { total: parsed.total, updated: parsed.updated, marks: unique });
      found.relevant = unique.filter((m) => m.classes.some((c) => classes.includes(c)));
      if (unique.length < parsed.total) errors.push(`trademarks read ${reading}: ${parsed.total - unique.length} of ${parsed.total} marks not read (open ${url})`);
    } catch (e) {
      errors.push(`trademarks for ${reading}: ${e.cause?.code ?? e.message}`);
    }
    out.push(found);
  }
  return { trademarks: out, errors };
}

async function check({ name, spellings }, opts, index, total) {
  const tag = `[${index + 1}/${total}]`;
  const [store, tm] = await Promise.all([
    appStoreFor(spellings, opts.quick, tag),
    opts.tm ? trademarksFor(spellings, opts.classes, tag) : { trademarks: null, errors: [] },
  ]);
  const labels = [...new Set(spellings.map(asciiLabel).filter(Boolean))];
  const domains = [];
  for (const label of labels) for (const tld of opts.tlds) domains.push(await domain(label, tld));
  return {
    name,
    spellings,
    appStore: store.appStore,
    trademarks: tm.trademarks,
    domains,
    links: manualLinks(spellings),
    errors: [...store.errors, ...tm.errors],
  };
}

const cell = (s) => String(s).replace(/\|/g, '\\|').replace(/\n/g, ' ');

function markdown(r, opts) {
  const out = [`## ${r.name}`, '', `Spellings searched: ${r.spellings.join(' · ')}`, ''];
  if (r.appStore.length) {
    out.push(`**App Store (Japan):** ${r.appStore.length} app(s) whose name contains a spelling.`, '');
    out.push('| Match | App | Seller | Genre | Released | Found by |', '|---|---|---|---|---|---|');
    let contains = 0;
    for (const a of r.appStore) {
      if (a.match === 'contains' && (contains += 1) > opts.maxContains) continue;
      const app = `[${cell(a.app)}](${a.url})${a.iPadOnly ? ' (iPad only)' : ''}`;
      out.push(`| ${a.match} | ${app} | ${cell(a.seller)} | ${cell(a.genre)} | ${a.released} | ${cell(a.term)} |`);
    }
    if (contains > opts.maxContains) out.push('', `…and ${contains - opts.maxContains} more "contains" rows (--max-contains, or --json for all).`);
  } else {
    out.push('**App Store (Japan):** no app name contains these spellings.');
  }
  if (r.trademarks) {
    for (const t of r.trademarks) {
      const shown = Number.isNaN(t.total) ? t.marks.length : t.total;
      out.push('', `**Trademarks read ${t.reading}** (patent-i.com, JPO data of ${t.updated || 'unknown date'}): ${shown} mark(s); ${t.relevant.length} in class ${opts.classes.join('/')} among the ${t.marks.length} read. ${t.url}`);
      if (t.relevant.length) {
        out.push('', '| Number | Mark | Holder | Classes | Filed | Registered |', '|---|---|---|---|---|---|');
        for (const m of t.relevant) {
          out.push(`| [${m.number}](${m.url}) | ${cell(m.mark || '(figurative)')} | ${cell(m.holder)} | ${m.classes.join(', ')} | ${m.filed} | ${m.registered || '–'} |`);
        }
      }
      if (t.marks.length < shown) out.push('', `Only the ${t.marks.length} newest of ${shown} were read; open the page for the rest.`);
    }
    if (!r.trademarks.length) out.push('', '**Trademarks:** no kana spelling given, so none looked up.');
  }
  out.push('');
  out.push(r.domains.length
    ? `**Domains (RDAP):** ${r.domains.map((d) => `${d.domain} ${d.status}`).join(' · ')}`
    : '**Domains (RDAP):** none checked (no ASCII spelling).');
  out.push('');
  out.push('**Check by hand:**');
  out.push(`- Google Play: ${r.links.googlePlay.join(' · ')}`);
  out.push(`- J-PlatPat 商標検索, 称呼(類似検索) with 類似群コード (see due-diligence.md): ${r.links.jPlatPat}`);
  out.push(`- J-PlatPat 簡易検索 (exact text and reading only): ${r.links.jPlatPatQuick.join(' · ')}`);
  if (r.links.jprs.length) out.push(`- .jp (JPRS WHOIS): ${r.links.jprs.join(' · ')}`);
  if (r.links.x.length) out.push(`- X: ${r.links.x.join(' · ')}`);
  if (r.links.instagram.length) out.push(`- Instagram: ${r.links.instagram.join(' · ')}`);
  if (r.errors.length) out.push('', `**Not checked (Unverified):** ${r.errors.join('; ')}`);
  return out.join('\n');
}

function parseArgs(argv) {
  const opts = { tlds: DEFAULT_TLDS, json: false, maxContains: DEFAULT_MAX_CONTAINS, tm: false, classes: DEFAULT_CLASSES, quick: false, candidates: [] };
  const list = (i, flag) => {
    const v = argv[i];
    if (!v) usage(`${flag} needs a comma-separated list`);
    return v.split(',').map((t) => t.trim()).filter(Boolean);
  };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--json') opts.json = true;
    else if (a === '--tm') opts.tm = true;
    else if (a === '--quick') opts.quick = true;
    else if (a === '--max-contains') {
      opts.maxContains = Number(argv[++i]);
      if (!Number.isInteger(opts.maxContains) || opts.maxContains < 0) usage('--max-contains needs a whole number');
    } else if (a === '--classes') {
      opts.classes = list(++i, a).map(Number);
      if (opts.classes.some((c) => !Number.isInteger(c) || c < 1 || c > 45)) usage('--classes takes Nice classes 1-45');
    } else if (a === '--tlds') opts.tlds = list(++i, a).map((t) => t.replace(/^\./, '').toLowerCase());
    else if (a.startsWith('--')) usage(`unknown option: ${a}`);
    else {
      const spellings = [...new Set(a.split('|').map((s) => s.trim()).filter(Boolean))];
      if (spellings.length) opts.candidates.push({ name: spellings[0], spellings });
    }
  }
  return opts;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const opts = parseArgs(process.argv.slice(2));
  if (!opts.candidates.length) usage();
  const results = [];
  for (const [i, c] of opts.candidates.entries()) results.push(await check(c, opts, i, opts.candidates.length));
  console.log(opts.json ? JSON.stringify(results, null, 2) : results.map((r) => markdown(r, opts)).join('\n\n'));
}
