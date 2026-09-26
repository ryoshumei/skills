# Due diligence for Japanese names

Run these checks on finalists only. The goal is a fair first screen with evidence, not legal clearance. Before anyone spends money on a name, a patent attorney (弁理士) should clear it.

Contents: the scripted check, app stores, trademarks, web search, domains and handles, the meaning screen, verdicts. Facts below were checked on 2026-09-26.

## 1. The scripted check

```sh
node <skill-dir>/scripts/check-names.mjs "アサヒ|あさひ|ASAHI" "みなも|ミナモ|水面|minamo"
node <skill-dir>/scripts/check-names.mjs --tlds com,app,ai --json "…"
```

- **Give every spelling:** katakana, hiragana, kanji and romaji. Apple's search is fuzzy but literal about script. In one test, a katakana search returned 185 apps and missed the app whose name was the same word in Latin letters, while the Latin spelling found it at once.
- **App Store (Japan):** the script uses the iTunes Search API (`country=jp`, `limit=200`). It searches twice per spelling, because `entity=software` leaves out iPad-only apps and `iPadSoftware` finds them. It lists every app whose name contains a spelling, folding width, case and katakana to hiragana.
  - "exact" means the app's name, before any subtitle, equals the spelling.
  - "exact (reading)" means a reading in parentheses equals it, as in 「SOELU(ソエル)」. Treat it as the same name, because people will say it the same way.
  - A common spelling such as mio can match dozens of apps. The table shows every exact match and the first 12 "contains" rows; `--max-contains N` or `--json` shows more.
- **Rate limits:** Apple allows about 20 searches a minute and sometimes answers 403 even below that. The script waits 3.2 s between calls, retries twice, and lists any search that still failed as Unverified. Each spelling takes two calls, so a name with four spellings takes about 25 seconds.
- **Domains:** for each ASCII spelling, the script asks the TLD's RDAP server (from IANA's bootstrap file). The default TLDs are .com and .app.
  - 200 means registered, and 404 means not registered.
  - A 429 or a TLD with no RDAP server (.jp and .io have none) is unknown, never available.
- A hit is a finding, not an error, so the exit code stays 0.

## 2. App stores

- **Google Play (Japan):** Play has no public search API, and its robots.txt disallows `/store/search`, so don't script it. Open the links the script prints (`hl=ja&gl=JP`) and read the first screen of results. Note each app's name, developer and install count.
- An app with the same name in health, lifestyle, AI or productivity is **Blocked** or **Caution**, depending on how close its purpose is. Record its name, developer, release date and URL.

## 3. Trademarks

**First pass, scripted (`--tm`):** the script reads patent-i.com's list of Japanese marks with each kana spelling's exact reading. The list is a mirror of JPO data with its update date on the page, and the site's robots.txt allows this at 5-second intervals. The script flags marks in the relevant classes (`--classes`, default 9, 42 and 44).
- It reads only the first page, the 10 newest marks, because later pages need a browser. A longer list is reported as partly unread; open the page for the rest.
- It matches the exact reading only: ソエル does not find marks read ソエール. Pass likely variants, such as long vowels and small kana, as extra spellings.
- It is a secondary source. A hit is strong evidence for Blocked, but a clean result still needs step 2 below.

**Final say, by hand:** J-PlatPat is the Japanese register. It has no URL search, and its terms ban automated access (「ロボットアクセス…禁止」), so run it by hand in a browser and have the owner paste the result list if you can't.

1. Open 商標検索: https://www.j-platpat.inpit.go.jp/t0100
2. In 商標(マーク), choose **称呼(類似検索)** and type the reading in full-width katakana (アサヒ). It finds similar-sounding marks as well as the exact reading. A search can use it twice at most, so split longer lists.
3. In 商品・役務, add **類似群コード** for the product's goods and services. Codes in one field are ORed when separated by spaces. For a patient-side health app, use `11C01 42X11 42V02`:
   - `11C01`: class 9, ダウンロード可能なコンピュータソフトウェア用アプリケーション (downloadable apps).
   - `42X11`: class 42, オンラインによるアプリケーションソフトウェアの提供（ＳａａＳ） (online software). The examination guide presumes class 9 programs similar to this, so always check both.
   - `42V02`: class 44, 医療情報の提供, 遠隔医療 (medical information and telemedicine).
4. For each relevant mark, record its registration or application number, holder, classes, 類似群コード and status (registered, pending or expired).

These codes come from 類似商品・役務審査基準 (Nice 13-2026, for applications from 2026-01-01). Other kinds of product need their own codes, which the guide lists by class.

- **Quick look:** the script also prints J-PlatPat 簡易検索 links. Those match exact text and readings only, so they don't replace step 2.
- **WIPO Global Brand Database** includes Japan's national marks. Its terms forbid automated queries, so use it by hand as a cross-check.
- **TMview** also carries JPO data, but it matches text, not readings. A clean result there, or on the web, is Unverified for Japan, not Clean.

## 4. Web search

For each spelling, search:

- `"<name>" 商標` and `"<name>" 登録商標`
- `"<name>" アプリ` and `"<name>" サービス`
- `"<romaji>" app` and `"<romaji>" trademark`

Note companies, clinics and products with the same name, especially in health.

## 5. Domains and handles

- **.jp:** the script prints a JPRS WHOIS link (`https://whois.jprs.jp/?type=DOM&key=<name>.jp`). Open it by hand, because JPRS limits use to its stated purposes and blocks rapid repeated queries.
  - A registered name shows a record.
  - 「該当するデータがありません。」 means no record. That doesn't guarantee the name can be registered.
- **Handles:** X and Instagram need a login to tell a free handle from a taken one. Open the links the script prints, and mark a handle Unverified if a login wall hides it.
- A taken domain is a Caution, not a Block, because a variant such as `get<name>.app` or `<name>-app.jp` works.

## 6. The meaning screen

Check every finalist in the three languages its readers will bring to it:

- **Japanese:** homophones and near-homophones, including in hiragana (かみ can be 紙, 髪 or 神).
  - Split readings: check where a hiragana name breaks into other words.
  - Kanji with two readings: 守 can be もり or まもり.
  - Slang, regional meanings, and how the name sounds next to 先生.
- **English:** the romaji spelling as an English word or part of one, and any rude or silly reading.
- **Chinese:** the kanji's Chinese meaning. For example, 確 suggests 确诊 ("a confirmed diagnosis").
- **Health-product traps:** work through the list in [methodology.md](methodology.md).

## 7. Verdicts

Give each finalist one verdict with evidence:

| Verdict | Meaning |
|---|---|
| **Clean** | Every check ran and found nothing close. |
| **Caution** | A similar name exists in a different field, a domain is taken, or a meaning needs care. Say what and why. |
| **Blocked** | The same or a confusingly similar name exists in health, AI or apps, or is a registered mark in a relevant class. |
| **Unverified** | A check could not run. Name the check and the next step. |

Evidence is a URL, a registration number, or an app's name with its developer and release date. List what each check found, even when it found nothing.
