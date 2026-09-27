#!/usr/bin/env python3
"""kune-trace ledger: traceable records built from conversations.

One CLI over a ledger folder (default: ./kune-ledger):

    ledger.json   meta: format version, profile, time zone, created_at
    log.jsonl     the only authoritative store: append-only, hash-chained events
    views/        generated HTML and the last check result (safe to delete)

Every write command appends exactly one event and prints the new id first.
State is always rebuilt from log.jsonl. Standard library only (Python 3.9+),
UTF-8 everywhere, no network access. The format and every command are in
references/ledger-format.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # Python 3.8 or a build without zoneinfo
    ZoneInfo = None

    class ZoneInfoNotFoundError(KeyError):
        """Stand-in so the fallback path below still works."""


FORMAT = "kune-trace-ledger"
FORMAT_VERSION = 1
GENESIS = "0" * 64
DEFAULT_DIR = "kune-ledger"
DEFAULT_TZ = "Asia/Tokyo"
DEFAULT_PROFILE = "health-visit"

ACTORS = ("her", "claude")
SOURCE_KINDS = ("chat", "voice", "photo", "document", "calendar", "other_ai")
DOC_KINDS = ("visit-memo", "record", "timeline")
TYPES = ("quoted", "document", "self", "guess")
FACT_TYPES = ("quoted", "document", "self")
PAPER_KINDS = ("photo", "document")
OPS = ("add_source", "add_doc", "add_line", "revise_line", "promote", "approve", "note")
RULE_NAMES = {1: "chain", 2: "cites", 3: "quotes", 4: "types", 5: "time", 6: "approval"}

# Labels per profile. The engine only knows the codes; a profile names them.
PROFILES = {
    "health-visit": {
        "types": {
            "quoted": "医師の言葉",
            "document": "書類",
            "self": "本人",
            "guess": "推測（未確認）",
        },
        "type_help": {
            "quoted": "先生の言葉。本人の記録から、原文のまま",
            "document": "処方箋・薬の説明書・検査結果などに書いてあること",
            "self": "本人の言葉・本人の申告",
            "guess": "本人やAIの推測。まだ確認されていません",
        },
        "doc_kinds": {"visit-memo": "受診メモ", "record": "記録", "timeline": "時系列"},
        "source_kinds": {
            "chat": "チャット",
            "voice": "音声",
            "photo": "写真",
            "document": "文書",
            "calendar": "カレンダー",
            "other_ai": "AIの回答",
        },
    },
}

# Zones with no daylight saving time, used when the machine has no zoneinfo
# data (for example Windows without the tzdata package).
FIXED_FALLBACK_MINUTES = {"Asia/Tokyo": 9 * 60, "Japan": 9 * 60}
WEEKDAYS_JA = "月火水木金土日"

SOURCE_ID_RE = re.compile(r"^S\d{4,}$")
DOC_ID_RE = re.compile(r"^D\d{4,}$")
LINE_ID_RE = re.compile(r"^L\d{4,}$")
NOTE_ID_RE = re.compile(r"^N\d{4,}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
MEDIA_TIME_RE = re.compile(r"^\d{1,3}:[0-5]\d(:[0-5]\d)?$")
OFFSET_RE = re.compile(r"^([+-])(\d{2}):?(\d{2})$")
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
DATETIME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(Z|[+-]\d{2}:?\d{2})?$")


class LedgerError(Exception):
    """A refused command: printed as ``error: ...`` with exit code 2."""


# ----------------------------------------------------------------- the clock

def system_now():
    """The system clock, in UTC. The only source of "now" in this script."""
    return dt.datetime.now(dt.timezone.utc)


def fmt_offset(delta):
    minutes = int(delta.total_seconds() // 60)
    sign = "-" if minutes < 0 else "+"
    minutes = abs(minutes)
    return "%s%02d:%02d" % (sign, minutes // 60, minutes % 60)


def resolve_tz(name):
    """Time zone name or offset -> (tzinfo, fallback note or None)."""
    name = (name or "").strip()
    if name in ("UTC", "Etc/UTC", "Z"):
        return dt.timezone.utc, None
    m = OFFSET_RE.match(name)
    if m:
        hours, minutes = int(m.group(2)), int(m.group(3))
        if hours > 23 or minutes > 59:
            raise LedgerError("bad UTC offset %r (use +09:00 style)" % name)
        sign = -1 if m.group(1) == "-" else 1
        return dt.timezone(sign * dt.timedelta(hours=hours, minutes=minutes)), None
    try:
        if ZoneInfo is None:
            raise ZoneInfoNotFoundError(name)
        return ZoneInfo(name), None
    except (ZoneInfoNotFoundError, ValueError, OSError):
        if name in FIXED_FALLBACK_MINUTES:
            offset = dt.timedelta(minutes=FIXED_FALLBACK_MINUTES[name])
            note = ("zoneinfo data for %s is missing on this machine; using the fixed offset %s"
                    % (name, fmt_offset(offset)))
            return dt.timezone(offset), note
        raise LedgerError(
            "time zone %r was not found (no zoneinfo data on this machine, or a wrong name). "
            "Install the tzdata package, or use an IANA name such as Asia/Tokyo or a fixed offset "
            "such as +09:00" % name)


def now_in(tzinfo):
    return system_now().astimezone(tzinfo).replace(microsecond=0)


def weekday_ja(day):
    return WEEKDAYS_JA[day.weekday()]


def date_ja(day):
    return "%d年%d月%d日（%s曜日）" % (day.year, day.month, day.day, weekday_ja(day))


def parse_at(value):
    """A stored ISO 8601 instant (with offset) -> aware datetime, or None."""
    try:
        parsed = dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def parse_absolute(value, tzinfo):
    """--happened-at: an absolute ISO date or datetime -> its stored form."""
    raw = (value or "").strip()
    m = DATE_RE.match(raw)
    if m:
        try:
            day = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            raise LedgerError("--happened-at %r is not a real date" % raw)
        return day.isoformat()
    m = DATETIME_RE.match(raw)
    if m:
        y, mo, d, h, mi = (int(m.group(i)) for i in range(1, 6))
        s = int(m.group(6) or 0)
        zone = m.group(7)
        if zone == "Z":
            tz = dt.timezone.utc
        elif zone:
            tz, _ = resolve_tz(zone)
        else:
            tz = tzinfo
        try:
            when = dt.datetime(y, mo, d, h, mi, s, tzinfo=tz)
        except ValueError:
            raise LedgerError("--happened-at %r is not a real date and time" % raw)
        return when.isoformat()
    words = find_relative_time(raw)
    if words or raw.lower() in ("now", "today", "yesterday", "tomorrow"):
        word = words[0] if words else raw
        raise LedgerError(
            "--happened-at must be absolute; 「%s」 is relative. Convert it with `ledger.py now --days N`, "
            "confirm the date with her, then pass YYYY-MM-DD" % word)
    raise LedgerError(
        "--happened-at must be an absolute ISO date or datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM[+09:00]), "
        "got %r" % raw)


def is_absolute(value):
    if not isinstance(value, str):
        return False
    if DATE_RE.match(value):
        return True
    return parse_at(value) is not None


# ------------------------------------------------------- relative time words

_REL_WORDS = sorted({
    "今日", "本日", "明日", "昨日", "一昨日", "明後日", "さっき", "先ほど", "先程", "さきほど",
    "今朝", "今夜", "今晩", "昨夜", "昨晩", "明朝", "昨朝",
    "先週", "今週", "来週", "再来週", "先々週", "先月", "今月", "来月", "再来月", "先々月",
    "去年", "昨年", "今年", "来年", "一昨年", "おととし",
    "この前", "このあいだ", "先日",
    "きのう", "おととい", "おとつい", "あさって", "あした", "けさ", "ゆうべ",
}, key=lambda w: (-len(w), w))
_NUM = r"(?:[0-9０-９]+|[一二三四五六七八九十百千数何]+)"
_UNIT = r"(?:日|週間|週|か月|ヶ月|カ月|ケ月|ヵ月|箇月|年|時間|分)"
_REL_PATTERNS = [
    # N日前 / N日後 / 数日前 / 2週間後 ... but not a calendar date such as 9月18日前
    r"(?<![0-9０-９一二三四五六七八九十百千数何月])" + _NUM + r"\s*" + _UNIT
    + r"\s*か?\s*(?:ほど|くらい|ぐらい|位)?\s*(?:前|後)(?![半期])",
    r"(?i:\b(?:\d+\s+(?:minutes?|hours?|days?|weeks?|months?|years?)\s+)?ago\b)",
    r"(?i:\b(?:yesterday|today|tonight|tomorrow|last\s+night|the\s+other\s+day"
    r"|this\s+(?:morning|afternoon|evening|week|month|year)|(?:last|next)\s+(?:week|month|year))\b)",
    r"きょう(?=は|も|の|、|。|に|で|から|まで|じゅう|中|\s|$|[,.!?！？」』）)])",
    r"こんや(?!く)",
] + [re.escape(w) for w in _REL_WORDS]
_REL_RE = re.compile("|".join(_REL_PATTERNS))


def find_relative_time(text):
    """Relative time expressions in ``text`` (distinct, in order of appearance)."""
    found = []
    for m in _REL_RE.finditer(text or ""):
        word = m.group(0)
        if word not in found:
            found.append(word)
    return found


# ------------------------------------------------------------ JSON and hashes

def canonical(obj):
    """Canonical JSON: sorted keys, no spaces, UTF-8 characters as they are."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def event_hash(prev, rest):
    return hashlib.sha256((prev + canonical(rest)).encode("utf-8")).hexdigest()


def normalize_ws(text):
    """Whitespace normalization (the only one quotes get): runs -> one space."""
    return re.sub(r"\s+", " ", text or "").strip()


def quote_in(quote, text):
    q = normalize_ws(quote)
    return bool(q) and q in normalize_ws(text)


def quote_span(text, quote):
    """(start, end) of ``quote`` in the verbatim ``text``, whitespace-normalized; or None."""
    norm_chars, index = [], []
    in_ws = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if not in_ws and norm_chars:
                norm_chars.append(" ")
                index.append(i)
            in_ws = True
        else:
            norm_chars.append(ch)
            index.append(i)
            in_ws = False
    norm = "".join(norm_chars).rstrip()
    q = normalize_ws(quote)
    pos = norm.find(q) if q else -1
    if pos < 0:
        return None
    return index[pos], index[pos + len(q) - 1] + 1


def write_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def clean_text(value, what):
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise LedgerError("%s is empty" % what)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise LedgerError("%s is not valid UTF-8 text" % what)
    return text


def read_stdin_text():
    stream = getattr(sys.stdin, "buffer", None)
    raw = stream.read() if stream is not None else sys.stdin.read().encode("utf-8")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise LedgerError("stdin is not UTF-8")


def problem(rule, ident, message):
    return {"rule": rule, "name": RULE_NAMES[rule], "id": ident, "message": message}


# ------------------------------------------------------------ ledger folder

class Ledger:
    """The files of one ledger folder."""

    def __init__(self, path):
        self.dir = Path(path)
        self.meta_path = self.dir / "ledger.json"
        self.log_path = self.dir / "log.jsonl"
        self.views = self.dir / "views"
        self.check_path = self.views / "check.json"

    @property
    def shown(self):
        return self.dir.as_posix()

    def read_meta(self):
        if not self.meta_path.exists():
            raise LedgerError("no ledger in %s (run `ledger.py init --dir %s` first)" % (self.shown, self.shown))
        try:
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise LedgerError("%s is not valid JSON: %s" % (self.meta_path.as_posix(), exc))
        if meta.get("format") != FORMAT:
            raise LedgerError("%s is not a kune-trace ledger" % self.meta_path.as_posix())
        if meta.get("format_version") != FORMAT_VERSION:
            raise LedgerError("unsupported ledger format_version %r" % meta.get("format_version"))
        if meta.get("profile") not in PROFILES:
            raise LedgerError("unknown profile %r" % meta.get("profile"))
        return meta

    def read_events(self):
        """-> (events, problems, warnings, size, appendable). Checks rule 1 as it reads."""
        if not self.log_path.exists():
            raise LedgerError("%s is missing" % self.log_path.as_posix())
        raw = self.log_path.read_bytes()
        size = len(raw)
        problems, warnings, events = [], [], []
        if not raw:
            return events, problems, warnings, size, True
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            problems.append(problem(1, "log", "log.jsonl is not valid UTF-8 (byte %d): it was edited" % exc.start))
            text = raw.decode("utf-8", "replace")
        appendable = True
        if not text.endswith("\n"):
            problems.append(problem(1, "log", "log.jsonl does not end with a newline: it was cut or edited"))
        lines = text.split("\n")
        if text.endswith("\n"):
            lines = lines[:-1]
        prev_hash, prev_at, expect = GENESIS, None, 1
        for n, line in enumerate(lines, start=1):
            where = "line %d" % n
            try:
                ev = json.loads(line)
            except ValueError:
                problems.append(problem(1, where, "log.jsonl %s is not valid JSON: it was edited or cut" % where))
                if n == len(lines):
                    appendable = False
                continue
            if not isinstance(ev, dict) or set(ev) != {"seq", "at", "actor", "op", "data", "prev", "hash"}:
                problems.append(problem(1, where, "log.jsonl %s is not an event {seq, at, actor, op, data, prev, hash}" % where))
                if n == len(lines):
                    appendable = False
                continue
            ident = "#%s" % ev.get("seq")
            if line != canonical(ev):
                problems.append(problem(1, ident, "%s (%s) is not in canonical form: the line was edited by hand" % (ident, where)))
            if ev["seq"] != expect:
                problems.append(problem(1, ident, "%s: seq is %r, expected %d (an event is missing or out of order)"
                                        % (ident, ev["seq"], expect)))
            if ev["prev"] != prev_hash:
                problems.append(problem(1, ident, "%s: prev does not match the hash of the event before it "
                                        "(an earlier event was edited, removed or reordered)" % ident))
            rest = {k: ev[k] for k in ("seq", "at", "actor", "op", "data")}
            if not isinstance(ev["prev"], str) or event_hash(ev["prev"], rest) != ev["hash"]:
                problems.append(problem(1, ident, "%s: hash does not match its content (it was edited after it was written)" % ident))
            if ev["actor"] not in ACTORS:
                problems.append(problem(1, ident, "%s: actor %r is not her or claude" % (ident, ev["actor"])))
            when = parse_at(ev["at"])
            if when is None:
                problems.append(problem(1, ident, "%s: at %r is not an ISO 8601 time with an offset" % (ident, ev["at"])))
            elif prev_at is not None and when < prev_at:
                warnings.append(problem(1, ident, "%s: time %s is earlier than the event before it; was the clock changed?"
                                        % (ident, ev["at"])))
            if when is not None:
                prev_at = when
            events.append(ev)
            prev_hash = ev["hash"] if isinstance(ev["hash"], str) else prev_hash
            expect = (ev["seq"] + 1) if isinstance(ev["seq"], int) else expect + 1
        return events, problems, warnings, size, appendable

    def append(self, events, size, actor, op, data, when):
        if actor not in ACTORS:
            raise LedgerError("actor must be her or claude")
        prev = events[-1]["hash"] if events else GENESIS
        seq = (events[-1]["seq"] + 1) if events else 1
        rest = {"seq": seq, "at": when.isoformat(), "actor": actor, "op": op, "data": data}
        event = dict(rest, prev=prev, hash=event_hash(prev, rest))
        line = (canonical(event) + "\n").encode("utf-8")
        if self.log_path.stat().st_size != size:
            raise LedgerError("log.jsonl changed while this command ran; run it again")
        with open(str(self.log_path), "ab") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        return event

    def read_last_check(self):
        try:
            data = json.loads(self.check_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None


# -------------------------------------------------------------- materialize

class State:
    """Everything derived from the log. Never stored."""

    def __init__(self, meta):
        self.meta = meta
        self.sources, self.docs, self.lines, self.notes = {}, {}, {}, {}
        self.events, self.by_seq = [], {}
        self.problems = []

    @property
    def head(self):
        if not self.events:
            return {"seq": 0, "hash": GENESIS}
        return {"seq": self.events[-1]["seq"], "hash": self.events[-1]["hash"]}

    def kind_of(self, source_id):
        src = self.sources.get(source_id)
        return src["kind"] if src else None

    def apply(self, ev):
        self.events.append(ev)
        if isinstance(ev.get("seq"), int):
            self.by_seq[ev["seq"]] = ev
        op, data = ev.get("op"), ev.get("data")
        ident = "#%s" % ev.get("seq")
        if op not in OPS:
            self.problems.append(problem(1, ident, "%s: unknown op %r" % (ident, op)))
            return
        if not isinstance(data, dict):
            self.problems.append(problem(1, ident, "%s: data is not an object" % ident))
            return
        try:
            getattr(self, "_" + op)(ev, data)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            self.problems.append(problem(1, ident, "%s: malformed %s data (%s)" % (ident, op, exc)))

    # each op ---------------------------------------------------------
    def _add_source(self, ev, d):
        sid = d["id"]
        if not SOURCE_ID_RE.match(sid) or sid in self.sources:
            raise ValueError("bad or repeated source id %r" % sid)
        if d["kind"] not in SOURCE_KINDS:
            raise ValueError("unknown source kind %r" % d["kind"])
        if not isinstance(d["text"], str):
            raise TypeError("text must be a string")
        self.sources[sid] = {
            "id": sid, "kind": d["kind"], "text": d["text"],
            "speaker": d.get("speaker"), "file": d.get("file"), "page": d.get("page"),
            "media_time": d.get("media_time"), "happened_at": d.get("happened_at"),
            "happened_confirmed": bool(d.get("happened_confirmed", False)),
            "captured_at": ev["at"], "actor": ev["actor"], "seq": ev["seq"], "note_seqs": [],
        }

    def _add_doc(self, ev, d):
        did = d["id"]
        if not DOC_ID_RE.match(did) or did in self.docs:
            raise ValueError("bad or repeated doc id %r" % did)
        if d["kind"] not in DOC_KINDS:
            raise ValueError("unknown doc kind %r" % d["kind"])
        self.docs[did] = {"id": did, "title": d["title"], "kind": d["kind"], "for": d.get("for"),
                          "created_at": ev["at"], "seq": ev["seq"], "lines": []}

    def _add_line(self, ev, d):
        lid = d["id"]
        if not LINE_ID_RE.match(lid) or lid in self.lines:
            raise ValueError("bad or repeated line id %r" % lid)
        if d["type"] not in TYPES:
            raise ValueError("unknown type %r" % d["type"])
        cites = [clean_cite(c) for c in d["cites"]]
        line = {
            "id": lid, "doc": d["doc"], "text": d["text"], "type": d["type"], "cites": cites,
            "rev": 1, "status": "draft", "approved_rev": None,
            "created_at": ev["at"], "updated_at": ev["at"], "seqs": [ev["seq"]],
            "ever_guess": d["type"] == "guess", "guess_exit": None,
            "ai_pending": any(self.kind_of(c["source"]) == "other_ai" for c in cites),
        }
        self.lines[lid] = line
        if d["doc"] in self.docs:
            self.docs[d["doc"]]["lines"].append(lid)
        else:
            self.problems.append(problem(1, lid, "%s belongs to %s, which does not exist" % (lid, d["doc"])))

    def _revise_line(self, ev, d):
        line = self._line(d["line"])
        if not isinstance(d.get("reason"), str) or not d["reason"].strip():
            self.problems.append(problem(1, line["id"], "revise_line #%d has no reason" % ev["seq"]))
        old_type = line["type"]
        new_type = d.get("type", old_type)
        if new_type not in TYPES:
            raise ValueError("unknown type %r" % new_type)
        if "cites" in d:
            new_cites = [clean_cite(c) for c in d["cites"]]
            old_sources = {c["source"] for c in line["cites"]}
            if any(c["source"] not in old_sources and self.kind_of(c["source"]) == "other_ai" for c in new_cites):
                line["ai_pending"] = True
            line["cites"] = new_cites
        if "text" in d:
            line["text"] = d["text"]
        if old_type == "guess" and new_type != "guess":
            line["guess_exit"] = ("revise_line", ev["seq"])
        if new_type == "guess" and old_type != "guess":
            line["ever_guess"] = True
            line["guess_exit"] = None
        line["type"] = new_type
        self._changed(line, ev)

    def _promote(self, ev, d):
        line = self._line(d["line"])
        seq = ev["seq"]
        if line["type"] != "guess":
            self.problems.append(problem(4, line["id"], "promote #%d: %s was %s, not a guess; only a guess is promoted"
                                         % (seq, line["id"], line["type"])))
            return
        if d["to"] not in FACT_TYPES:
            raise ValueError("promote to %r" % d["to"])
        evidence, confirmed = d.get("evidence"), d.get("confirmed_by")
        if (evidence is None) == (confirmed is None):
            self.problems.append(problem(4, line["id"], "promote #%d needs exactly one of evidence {source} or "
                                         "confirmed_by her" % seq))
            return
        if confirmed is not None and (confirmed != "her" or ev["actor"] != "her"):
            self.problems.append(problem(4, line["id"], "promote #%d: confirmed_by must be her, written by her" % seq))
            return
        if evidence is not None:
            cite = clean_cite(evidence)
            if cite["source"] not in self.sources:
                self.problems.append(problem(4, line["id"], "promote #%d: evidence %s does not exist" % (seq, cite["source"])))
                return
            if cite not in line["cites"]:
                line["cites"].append(cite)
        line["type"] = d["to"]
        line["guess_exit"] = ("promote", seq)
        line["ai_pending"] = False
        self._changed(line, ev)

    def _approve(self, ev, d):
        items = d["lines"]
        if not isinstance(items, list) or not items:
            raise ValueError("approve needs lines")
        for item in items:
            lid, rev = item["line"], item["rev"]
            if ev["actor"] != "her":
                self.problems.append(problem(6, lid, "approve #%d was written by %s; only she approves"
                                             % (ev["seq"], ev["actor"])))
                continue
            line = self.lines.get(lid)
            if line is None:
                self.problems.append(problem(6, lid, "approve #%d: %s does not exist" % (ev["seq"], lid)))
                continue
            if rev != line["rev"]:
                self.problems.append(problem(6, lid, "approve #%d is for rev %s, but %s was at rev %d then"
                                             % (ev["seq"], rev, lid, line["rev"])))
                continue
            line["approved_rev"] = rev
            line["status"] = "approved"
            line["seqs"].append(ev["seq"])

    def _note(self, ev, d):
        nid = d["id"]
        if not NOTE_ID_RE.match(nid) or nid in self.notes:
            raise ValueError("bad or repeated note id %r" % nid)
        about = d.get("about")
        known = about is None or about in self.sources or about in self.docs or about in self.lines or about in self.notes
        if not known:
            self.problems.append(problem(1, nid, "%s is about %s, which does not exist" % (nid, about)))
        if "happened_at" in d:
            if about not in self.sources:
                self.problems.append(problem(1, nid, "%s sets happened_at, but %s is not a source" % (nid, about)))
            else:
                src = self.sources[about]
                src["happened_at"] = d["happened_at"]
                src["happened_confirmed"] = bool(d.get("happened_confirmed", False))
                src["note_seqs"].append(ev["seq"])
        if about in self.lines:
            self.lines[about]["seqs"].append(ev["seq"])
        self.notes[nid] = {"id": nid, "text": d["text"], "about": about, "happened_at": d.get("happened_at"),
                           "happened_confirmed": d.get("happened_confirmed"), "at": ev["at"],
                           "actor": ev["actor"], "seq": ev["seq"]}

    # helpers ---------------------------------------------------------
    def _line(self, lid):
        if lid not in self.lines:
            raise ValueError("line %r does not exist" % lid)
        return self.lines[lid]

    @staticmethod
    def _changed(line, ev):
        line["rev"] += 1
        line["status"] = "draft"
        line["updated_at"] = ev["at"]
        line["seqs"].append(ev["seq"])


def clean_cite(cite):
    if not isinstance(cite, dict) or not isinstance(cite.get("source"), str):
        raise TypeError("a cite is {source, quote?}")
    out = {"source": cite["source"]}
    if "quote" in cite:
        if not isinstance(cite["quote"], str):
            raise TypeError("quote must be a string")
        out["quote"] = cite["quote"]
    return out


def materialize(meta, events):
    state = State(meta)
    for ev in events:
        state.apply(ev)
    return state


# -------------------------------------------------------------- rules 2 - 6

def type_rule_errors(line_type, cites, state, ai_pending=False, guess_ok=True, label=None):
    """Rule 4 for one line (its current or proposed form). -> [message]."""
    labels = PROFILES[state.meta["profile"]]["types"]
    name = "%s (%s)" % (line_type, labels.get(line_type, line_type))
    who = label + " is " if label else "a line of type "
    errs = []
    if line_type == "quoted" and not any(
            c.get("quote") and state.kind_of(c["source"]) not in (None, "other_ai") for c in cites):
        errs.append("%s%s needs a cite with a verbatim quote from a source that isn't an AI answer "
                    "(--cite S0001:\"the words\")" % (who, name))
    if line_type == "document" and not any(state.kind_of(c["source"]) in PAPER_KINDS for c in cites):
        errs.append("%s%s needs a cite to a photo or document source" % (who, name))
    if line_type in FACT_TYPES and ai_pending:
        ai = [c["source"] for c in cites if state.kind_of(c["source"]) == "other_ai"]
        errs.append("%s%s but cites an AI answer (%s, other_ai) without a promote after it: "
                    "a line citing other_ai stays guess until promoted" % (who, name, ", ".join(ai) or "other_ai"))
    if line_type != "guess" and not guess_ok:
        errs.append("%s%s but was a guess, and no promote event made it one: a guess never becomes a fact silently"
                    % (who, name))
    return errs


def line_guess_ok(line):
    exit_ = line["guess_exit"]
    return not line["ever_guess"] or line["type"] == "guess" or (exit_ is not None and exit_[0] == "promote")


def run_rules(state):
    """Rules 2-6 on a materialized state. -> (errors, warnings)."""
    errors, warnings = [], []
    # 2. every line cites >= 1 existing source
    for line in state.lines.values():
        if not line["cites"]:
            errors.append(problem(2, line["id"], "%s cites no source" % line["id"]))
        for c in line["cites"]:
            if c["source"] not in state.sources:
                errors.append(problem(2, line["id"], "%s cites %s, which does not exist" % (line["id"], c["source"])))
    # 3. quotes are verbatim (whitespace normalization only)
    for line in state.lines.values():
        for c in line["cites"]:
            if "quote" not in c or c["source"] not in state.sources:
                continue
            src_text = state.sources[c["source"]]["text"]
            if not normalize_ws(c["quote"]):
                errors.append(problem(3, line["id"], "%s has an empty quote for %s" % (line["id"], c["source"])))
            elif not quote_in(c["quote"], src_text):
                errors.append(problem(3, line["id"], "%s: the quote 「%s」 is not in %s verbatim (only whitespace may "
                                      "differ). %s says: 「%s」" % (line["id"], c["quote"], c["source"], c["source"],
                                                                 _short(src_text, 80))))
    # 4. type rules
    for line in state.lines.values():
        for msg in type_rule_errors(line["type"], line["cites"], state, ai_pending=line["ai_pending"],
                                    guess_ok=line_guess_ok(line), label=line["id"]):
            errors.append(problem(4, line["id"], msg))
    # 5. absolute time in records; relative words in sources need a confirmed happened_at
    fix = "Convert it with `ledger.py now` (or `now --days N`), confirm the date with her, then"
    for line in state.lines.values():
        for word in find_relative_time(line["text"]):
            errors.append(problem(5, line["id"], "%s: relative time 「%s」 in the line text. Records need absolute dates. "
                                  "%s revise-line." % (line["id"], word, fix)))
    for doc in state.docs.values():
        for field in ("title", "for"):
            for word in find_relative_time(doc.get(field) or ""):
                errors.append(problem(5, doc["id"], "%s: relative time 「%s」 in the doc %s. %s add a doc with an "
                                      "absolute date." % (doc["id"], word, field, fix)))
    for src in state.sources.values():
        if src["happened_at"] is not None and not is_absolute(src["happened_at"]):
            errors.append(problem(5, src["id"], "%s: happened_at %r is not an absolute ISO date or datetime"
                                  % (src["id"], src["happened_at"])))
        words = find_relative_time(src["text"])
        if words and not (src["happened_at"] and src["happened_confirmed"]):
            warnings.append(problem(5, src["id"], "%s: the verbatim text has 「%s」 and no confirmed happened_at. %s "
                                    "record it: note --about %s --happened-at YYYY-MM-DD --confirmed --text \"...\""
                                    % (src["id"], "」「".join(words), fix, src["id"])))
    # 6. approval problems were found while replaying the log
    return errors, warnings


def drafts_of(state):
    return [lid for lid, line in state.lines.items() if line["status"] != "approved"]


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def _short(text, n):
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


# ------------------------------------------------------------------- check

def run_check(led, save=True):
    meta = led.read_meta()
    tzinfo, _ = resolve_tz(meta["timezone"])
    events, chain_errors, chain_warnings, _size, _ok = led.read_events()
    state = materialize(meta, events)
    last = led.read_last_check()
    anchor = last.get("anchor") if last else None
    if isinstance(anchor, dict) and isinstance(anchor.get("seq"), int) and anchor["seq"] > 0:
        seen = state.by_seq.get(anchor["seq"])
        head_seq = state.head["seq"]
        if seen is None:
            chain_errors.append(problem(1, "#%d" % anchor["seq"], "the last check saw event #%d, but the log now ends at "
                                        "#%d: events were removed" % (anchor["seq"], head_seq)))
        elif seen["hash"] != anchor.get("hash"):
            chain_errors.append(problem(1, "#%d" % anchor["seq"], "event #%d is not what the last check saw: the log "
                                        "was rewritten" % anchor["seq"]))
    struct = [p for p in state.problems if p["rule"] == 1]
    other = [p for p in state.problems if p["rule"] != 1]
    rule_errors, rule_warnings = run_rules(state)
    errors = chain_errors + struct + sorted(other + rule_errors, key=lambda p: p["rule"])
    warnings = chain_warnings + rule_warnings
    checked_at = now_in(tzinfo)
    report = {
        "ok": not errors,
        "checked_at": checked_at.isoformat(),
        "ledger": led.shown,
        "head": state.head,
        "counts": {"events": len(events), "sources": len(state.sources), "docs": len(state.docs),
                   "lines": len(state.lines)},
        "errors": errors,
        "warnings": warnings,
        "drafts": drafts_of(state),
    }
    if save:
        chain_ok = not any(p["rule"] == 1 for p in errors)
        new_anchor = anchor if isinstance(anchor, dict) else None
        if chain_ok and state.events:
            new_anchor = state.head
        saved = {"checked_at": report["checked_at"], "ok": report["ok"], "errors": len(errors),
                 "warnings": len(warnings), "drafts": report["drafts"], "head": state.head, "anchor": new_anchor}
        try:
            write_atomic(led.check_path, json.dumps(saved, ensure_ascii=False, indent=2) + "\n")
        except OSError as exc:
            print("note: could not save %s (%s)" % (led.check_path.as_posix(), exc), file=sys.stderr)
    return report


def print_check(report):
    c = report["counts"]
    head = report["head"]
    print("check %s: %s, %s, %s, %s (head #%d %s)"
          % (report["ledger"], plural(c["events"], "event"), plural(c["sources"], "source"),
             plural(c["docs"], "doc"), plural(c["lines"], "line"), head["seq"], head["hash"][:8]))
    for sev, items in (("error", report["errors"]), ("warning", report["warnings"])):
        for p in items:
            msg, ident = p["message"], p["id"] or ""
            if ident and msg.startswith(ident + ": "):
                msg = msg[len(ident) + 2:]  # the id column already says it
            print("%-8s rule %d %-8s %-6s %s" % (sev, p["rule"], p["name"], ident, msg))
    if report["drafts"]:
        print("drafts   %s (not approved by her yet)" % ", ".join(report["drafts"]))
    print("result   %s (%s, %s)" % ("PASS" if report["ok"] else "FAIL", plural(len(report["errors"]), "error"),
                                      plural(len(report["warnings"]), "warning")))


# ------------------------------------------------------------------ writes

class Session:
    """A write in progress: the meta, the replayed state and the time."""

    def __init__(self, led):
        self.led = led
        self.meta = led.read_meta()
        self.tzinfo, self.tz_note = resolve_tz(self.meta["timezone"])
        self.events, problems, _warnings, self.size, appendable = led.read_events()
        if not appendable:
            raise LedgerError("cannot append: the last line of log.jsonl is not a valid event. Run check; "
                              "don't edit the log by hand")
        self.state = materialize(self.meta, self.events)
        broken = [p for p in problems if p["rule"] == 1]
        if broken:
            print("warning: the log chain is broken (%s). The new event is added, but check will fail until the "
                  "log is restored" % broken[0]["message"], file=sys.stderr)
        self.when = now_in(self.tzinfo)

    def next_id(self, prefix, existing):
        numbers = [int(i[1:]) for i in existing if i.startswith(prefix) and i[1:].isdigit()]
        return "%s%04d" % (prefix, (max(numbers) if numbers else 0) + 1)

    def append(self, actor, op, data):
        return self.led.append(self.events, self.size, actor, op, data, self.when)

    def labels(self):
        return PROFILES[self.meta["profile"]]


def append_event(ledger_dir, actor, op, data, at=None):
    """Append one hash-chained event WITHOUT the CLI's checks.

    Tests use this to craft logs that the CLI refuses to write, to prove that
    ``check`` still catches them. Claude never uses it.
    """
    led = Ledger(ledger_dir)
    meta = led.read_meta()
    tzinfo, _ = resolve_tz(meta["timezone"])
    events, _p, _w, size, _ok = led.read_events()
    when = (at or system_now()).astimezone(tzinfo).replace(microsecond=0)
    return led.append(events, size, actor, op, data, when)


def parse_cite(spec, state):
    """``S0003`` or ``S0003:verbatim quote`` -> {source, quote?}, checked against the sources."""
    source, sep, quote = spec.partition(":")
    source = source.strip()
    if not SOURCE_ID_RE.match(source):
        raise LedgerError("bad cite %r: use S0003 or S0003:\"verbatim quote\" (an ASCII colon)" % spec)
    if source not in state.sources:
        raise LedgerError("cite %s: no such source (see `ledger.py state`)" % source)
    cite = {"source": source}
    if sep:
        if not normalize_ws(quote):
            raise LedgerError("cite %s has an empty quote" % source)
        if not quote_in(quote, state.sources[source]["text"]):
            raise LedgerError("the quote 「%s」 is not in %s verbatim (only whitespace may differ). %s says: 「%s」"
                              % (quote, source, source, _short(state.sources[source]["text"], 120)))
        cite["quote"] = quote.strip()
    return cite


def refuse_type_errors(errs):
    if errs:
        raise LedgerError("; ".join(errs))


def event_note(ev):
    return "(%s #%d, %s)" % (ev["op"], ev["seq"], ev["at"])


def cmd_init(args):
    led = Ledger(args.dir)
    if led.meta_path.exists() or led.log_path.exists():
        raise LedgerError("a ledger already exists in %s; nothing was changed" % led.shown)
    if args.profile not in PROFILES:
        raise LedgerError("unknown profile %r (known: %s)" % (args.profile, ", ".join(PROFILES)))
    tzinfo, note = resolve_tz(args.tz)
    created = now_in(tzinfo)
    meta = {"format": FORMAT, "format_version": FORMAT_VERSION, "profile": args.profile,
            "timezone": args.tz, "created_at": created.isoformat()}
    if args.sample:
        meta["sample"] = True
    led.dir.mkdir(parents=True, exist_ok=True)
    led.views.mkdir(exist_ok=True)
    write_atomic(led.meta_path, json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    with open(str(led.log_path), "xb"):
        pass
    try:
        os.chmod(str(led.log_path), 0o600)  # her records: owner-only, like the other files written here
    except OSError:
        pass
    print("initialized %s (profile %s, time zone %s)" % (led.shown, args.profile, args.tz))
    if note:
        print("note     " + note)
    return 0


def cmd_now(args):
    led = Ledger(args.dir)
    tz_name = args.tz
    if tz_name is None:
        tz_name = DEFAULT_TZ
        if led.meta_path.exists():
            tz_name = led.read_meta()["timezone"]
    tzinfo, note = resolve_tz(tz_name)
    utc = system_now().astimezone(dt.timezone.utc).replace(microsecond=0)
    local = utc.astimezone(tzinfo)
    day = local.date()
    out = {"utc": utc.isoformat(), "local": local.isoformat(), "timezone": tz_name,
           "offset": fmt_offset(local.utcoffset()), "date": day.isoformat(), "weekday": weekday_ja(day),
           "date_ja": date_ja(day), "fallback": note is not None, "note": note}
    if args.days is not None:
        target = day + dt.timedelta(days=args.days)
        out["target"] = {"days": args.days, "date": target.isoformat(), "weekday": weekday_ja(target),
                         "date_ja": date_ja(target)}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print("utc      %s" % out["utc"])
    print("local    %s (%s)" % (out["local"], tz_name))
    print("date     %s %s %s" % (out["date"], out["weekday"], out["date_ja"]))
    if args.days is not None:
        t = out["target"]
        print("target   %s %s %s (%+d day%s)" % (t["date"], t["weekday"], t["date_ja"], args.days,
                                                 "" if abs(args.days) == 1 else "s"))
    if note:
        print("note     " + note)
    return 0


def cmd_add_source(args):
    s = Session(Ledger(args.dir))
    if (args.text is None) == (not args.stdin):
        raise LedgerError("give the verbatim text with exactly one of --text or --stdin")
    text = clean_text(read_stdin_text() if args.stdin else args.text, "the source text")
    if args.confirmed and not args.happened_at:
        raise LedgerError("--confirmed needs --happened-at (the date she confirmed)")
    data = {"id": s.next_id("S", s.state.sources), "kind": args.kind, "text": text}
    if args.speaker:
        data["speaker"] = clean_text(args.speaker, "--speaker")
    if args.file:
        data["file"] = clean_text(args.file, "--file").replace("\\", "/")
    if args.page is not None:
        if args.page < 1:
            raise LedgerError("--page starts at 1")
        data["page"] = args.page
    if args.media_time:
        if not MEDIA_TIME_RE.match(args.media_time):
            raise LedgerError("--media-time must look like 0:14 or 1:02:03")
        data["media_time"] = args.media_time
    if args.happened_at is not None:
        data["happened_at"] = parse_absolute(args.happened_at, s.tzinfo)
    data["happened_confirmed"] = bool(args.confirmed)
    ev = s.append(args.actor or "her", "add_source", data)
    print("%s  %s" % (data["id"], event_note(ev)))
    return 0


def cmd_add_doc(args):
    s = Session(Ledger(args.dir))
    data = {"id": s.next_id("D", s.state.docs), "title": clean_text(args.title, "--title"), "kind": args.kind}
    if args.for_:
        data["for"] = clean_text(args.for_, "--for")
    ev = s.append(args.actor or "claude", "add_doc", data)
    print("%s  %s" % (data["id"], event_note(ev)))
    return 0


def cmd_add_line(args):
    s = Session(Ledger(args.dir))
    if args.doc not in s.state.docs:
        raise LedgerError("no doc %s (see `ledger.py state`)" % args.doc)
    if not args.cite:
        raise LedgerError("a line needs at least one --cite S0001 (every line cites its source)")
    cites = [parse_cite(c, s.state) for c in args.cite]
    ai = any(s.state.kind_of(c["source"]) == "other_ai" for c in cites)
    if ai and args.type != "guess":
        raise LedgerError("%s is an AI answer (other_ai): a line citing it starts as guess. Make it a guess; "
                          "promote it later with evidence or her confirmation"
                          % ", ".join(c["source"] for c in cites if s.state.kind_of(c["source"]) == "other_ai"))
    refuse_type_errors(type_rule_errors(args.type, cites, s.state, ai_pending=ai))
    data = {"id": s.next_id("L", s.state.lines), "doc": args.doc, "text": clean_text(args.text, "--text"),
            "type": args.type, "cites": cites}
    ev = s.append(args.actor or "claude", "add_line", data)
    print("%s  %s" % (data["id"], event_note(ev)))
    return 0


def cmd_revise_line(args):
    s = Session(Ledger(args.dir))
    line = s.state.lines.get(args.line)
    if line is None:
        raise LedgerError("no line %s" % args.line)
    reason = clean_text(args.reason, "--reason")
    data = {"line": line["id"], "reason": reason}
    new_text = clean_text(args.text, "--text") if args.text is not None else line["text"]
    new_type = args.type or line["type"]
    new_cites = [parse_cite(c, s.state) for c in args.cite] if args.cite else line["cites"]
    if new_text != line["text"]:
        data["text"] = new_text
    if new_type != line["type"]:
        data["type"] = new_type
    if new_cites != line["cites"]:
        data["cites"] = new_cites
    if len(data) == 2:
        raise LedgerError("no change: give a different --text, --type or --cite")
    if line["type"] == "guess" and new_type != "guess":
        raise LedgerError("%s is a guess; a guess never becomes %s by a revision. Use `promote --line %s --to %s` "
                          "with --evidence S0007[:quote] or --confirmed-by-her" % (line["id"], new_type, line["id"], new_type))
    old_sources = {c["source"] for c in line["cites"]}
    added_ai = [c["source"] for c in new_cites
                if c["source"] not in old_sources and s.state.kind_of(c["source"]) == "other_ai"]
    if added_ai and new_type != "guess":
        raise LedgerError("%s is an AI answer (other_ai): a line citing it is a guess until promoted. Keep %s a fact "
                          "without it, or add a separate guess line" % (", ".join(added_ai), line["id"]))
    ai_pending = line["ai_pending"] or bool(added_ai)
    refuse_type_errors(type_rule_errors(new_type, new_cites, s.state, ai_pending=ai_pending, label=line["id"]))
    was_approved = line["status"] == "approved"
    ev = s.append(args.actor or "claude", "revise_line", data)
    print("%s  rev %d, draft%s  %s" % (line["id"], line["rev"] + 1, " (approval reset)" if was_approved else "",
                                       event_note(ev)))
    return 0


def cmd_promote(args):
    s = Session(Ledger(args.dir))
    line = s.state.lines.get(args.line)
    if line is None:
        raise LedgerError("no line %s" % args.line)
    if line["type"] != "guess":
        raise LedgerError("%s is %s, not a guess; only a guess is promoted" % (line["id"], line["type"]))
    data = {"line": line["id"], "from": "guess", "to": args.to}
    cites = list(line["cites"])
    if args.evidence:
        cite = parse_cite(args.evidence, s.state)
        data["evidence"] = cite
        if cite not in cites:
            cites.append(cite)
        actor = args.actor or "claude"
    else:
        if args.actor == "claude":
            raise LedgerError("--confirmed-by-her is written by her (actor her)")
        data["confirmed_by"] = "her"
        actor = "her"
    refuse_type_errors(type_rule_errors(args.to, cites, s.state, ai_pending=False, label=line["id"]))
    if args.reason:
        data["reason"] = clean_text(args.reason, "--reason")
    ev = s.append(actor, "promote", data)
    basis = "evidence %s" % data["evidence"]["source"] if "evidence" in data else "confirmed by her"
    print("%s  guess → %s, draft, %s  %s" % (line["id"], args.to, basis, event_note(ev)))
    return 0


def cmd_approve(args):
    if args.actor == "claude":
        raise LedgerError("only she approves: approve is written as her, after she says yes to the exact text")
    s = Session(Ledger(args.dir))
    if args.line:
        line = s.state.lines.get(args.line)
        if line is None:
            raise LedgerError("no line %s" % args.line)
        if line["status"] == "approved":
            raise LedgerError("%s is already approved at rev %d" % (line["id"], line["rev"]))
        targets = [line]
        data = {"lines": [{"line": line["id"], "rev": line["rev"]}]}
    else:
        doc = s.state.docs.get(args.doc)
        if doc is None:
            raise LedgerError("no doc %s" % args.doc)
        targets = [s.state.lines[lid] for lid in doc["lines"] if s.state.lines[lid]["status"] != "approved"]
        if not targets:
            raise LedgerError("no draft lines in %s: every line is already approved" % doc["id"])
        data = {"doc": doc["id"], "lines": [{"line": l["id"], "rev": l["rev"]} for l in targets]}
    ev = s.append("her", "approve", data)
    print("%s  approved  %s" % (",".join(l["id"] for l in targets), event_note(ev)))
    return 0


def cmd_note(args):
    s = Session(Ledger(args.dir))
    st = s.state
    data = {"id": s.next_id("N", st.notes), "text": clean_text(args.text, "--text")}
    if args.about:
        if not (args.about in st.sources or args.about in st.docs or args.about in st.lines or args.about in st.notes):
            raise LedgerError("no %s to write a note about" % args.about)
        data["about"] = args.about
    if args.confirmed and not args.happened_at:
        raise LedgerError("--confirmed needs --happened-at")
    if args.happened_at is not None:
        if args.about not in st.sources:
            raise LedgerError("--happened-at sets a source's date: use --about S0001")
        data["happened_at"] = parse_absolute(args.happened_at, s.tzinfo)
        data["happened_confirmed"] = bool(args.confirmed)
    actor = args.actor or ("her" if args.confirmed else "claude")
    ev = s.append(actor, "note", data)
    print("%s  %s" % (data["id"], event_note(ev)))
    return 0


# ------------------------------------------------------------------- reads

def load_state(led):
    meta = led.read_meta()
    events, problems, _w, _s, _ok = led.read_events()
    state = materialize(meta, events)
    return state, problems


def state_json(state, led):
    def src(s):
        return {k: s[k] for k in ("id", "kind", "text", "speaker", "file", "page", "media_time", "happened_at",
                                  "happened_confirmed", "captured_at", "actor")}

    def line(l):
        return {k: l[k] for k in ("id", "doc", "text", "type", "cites", "status", "rev", "created_at", "updated_at")}

    return {
        "ledger": led.shown, "meta": state.meta, "head": state.head,
        "sources": [src(s) for s in state.sources.values()],
        "docs": [dict({k: d[k] for k in ("id", "title", "kind", "for", "created_at")},
                      lines=[line(state.lines[lid]) for lid in d["lines"]]) for d in state.docs.values()],
        "notes": [{k: n[k] for k in ("id", "text", "about", "happened_at", "happened_confirmed", "at", "actor")}
                  for n in state.notes.values()],
    }


def fmt_cites(cites):
    return ", ".join(c["source"] + (' "%s"' % c["quote"] if "quote" in c else "") for c in cites)


def cmd_state(args):
    led = Ledger(args.dir)
    state, problems = load_state(led)
    if args.json:
        print(json.dumps(state_json(state, led), ensure_ascii=False, indent=2))
        return 0
    meta, head = state.meta, state.head
    labels = PROFILES[meta["profile"]]
    last = ("  last change %s" % state.events[-1]["at"]) if state.events else ""
    print("%s  %s  %s  %d events  head #%d %s%s%s" % (led.shown, meta["profile"], meta["timezone"], len(state.events),
                                                      head["seq"], head["hash"][:8], last,
                                                      "  (sample)" if meta.get("sample") else ""))
    if problems:
        print("warning: the log chain is broken; run check")
    print("sources")
    if not state.sources:
        print("  (none)")
    for s in state.sources.values():
        extra = [x for x in (s["speaker"], s["file"], s["page"] and "p.%d" % s["page"], s["media_time"]) if x]
        print("  %s  %-8s  %s  「%s」%s" % (s["id"], s["kind"], s["captured_at"], _short(s["text"], 60),
                                           ("  " + " ".join(extra)) if extra else ""))
        if s["happened_at"]:
            print("         happened %s (%s)" % (s["happened_at"], "confirmed" if s["happened_confirmed"] else "unconfirmed"))
    print("docs")
    if not state.docs:
        print("  (none)")
    for d in state.docs.values():
        print("  %s  %s  %s%s" % (d["id"], d["kind"], d["title"], ("  for " + d["for"]) if d.get("for") else ""))
        for lid in d["lines"]:
            l = state.lines[lid]
            print("    %s  %s (%s)  %s rev %d  %s" % (l["id"], l["type"], labels["types"][l["type"]], l["status"],
                                                   l["rev"], l["text"]))
            print("           cites %s" % fmt_cites(l["cites"]))
    if state.notes:
        print("notes")
        for n in state.notes.values():
            print("  %s  %s%s" % (n["id"], ("about %s  " % n["about"]) if n["about"] else "", n["text"]))
    return 0


def history_entries(state, line_id):
    return [state.by_seq[seq] for seq in state.lines[line_id]["seqs"]]


def cmd_history(args):
    led = Ledger(args.dir)
    state, _problems = load_state(led)
    line = state.lines.get(args.line)
    if line is None:
        raise LedgerError("no line %s" % args.line)
    labels = PROFILES[state.meta["profile"]]["types"]
    print("%s  %s (%s)  %s  rev %d  in %s" % (line["id"], line["type"], labels[line["type"]], line["status"],
                                              line["rev"], line["doc"]))
    rev = 0
    for ev in history_entries(state, line["id"]):
        d = ev["data"]
        op = ev["op"]
        if op == "add_line":
            rev = 1
            what = "rev 1: %s 「%s」 cites %s" % (d["type"], d["text"], fmt_cites(d["cites"]))
        elif op == "revise_line":
            rev += 1
            parts = []
            if "text" in d:
                parts.append("text 「%s」" % d["text"])
            if "type" in d:
                parts.append("type %s" % d["type"])
            if "cites" in d:
                parts.append("cites %s" % fmt_cites(d["cites"]))
            what = "rev %d: %s; reason: %s" % (rev, ", ".join(parts), d.get("reason"))
        elif op == "promote":
            rev += 1
            basis = ("evidence %s" % fmt_cites([d["evidence"]])) if "evidence" in d else "confirmed by her"
            what = "rev %d: guess → %s, %s" % (rev, d["to"], basis)
        elif op == "approve":
            revs = [i["rev"] for i in d["lines"] if i["line"] == line["id"]]
            what = "rev %s approved by %s" % (revs[0] if revs else "?", ev["actor"])
        else:
            what = "note %s: %s" % (d.get("id"), d.get("text"))
        print("#%-4d %s  %-6s  %-11s  %s" % (ev["seq"], ev["at"], ev["actor"], op, what))
    return 0


def cmd_check(args):
    report = run_check(Ledger(args.dir))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_check(report)
    return 0 if report["ok"] else 1


def cmd_render(args):
    import ledger_view

    led = Ledger(args.dir)
    state, problems = load_state(led)
    if args.doc and args.doc not in state.docs:
        raise LedgerError("no doc %s" % args.doc)
    tzinfo, _ = resolve_tz(state.meta["timezone"])
    now = now_in(tzinfo)
    model = build_view_model(state, led, tzinfo, now, args.doc, chain_broken=bool(problems))
    html = ledger_view.render_page(model)
    if args.out:
        out = Path(args.out)
    else:
        out = led.views / ("%s.html" % args.doc if args.doc else "index.html")
    write_atomic(out, html)
    print("wrote %s" % out.as_posix())
    return 0


# -------------------------------------------------------------- view model

def fmt_local(value, tzinfo):
    when = parse_at(value)
    if when is None:
        return str(value)
    return when.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M")


def local_date(value, tzinfo):
    if isinstance(value, str) and DATE_RE.match(value):
        return dt.date.fromisoformat(value)
    when = parse_at(value)
    return when.astimezone(tzinfo).date() if when else None


def fmt_happened(src, tzinfo):
    value = src["happened_at"]
    if not value:
        return "未設定（記録した時刻のみ）"
    if not is_absolute(value):
        return "%s（形式が正しくありません：check を実行してください）" % value
    day = local_date(value, tzinfo)
    status = "確認済み" if src["happened_confirmed"] else "未確認"
    if DATE_RE.match(value):
        return "%s（%s）・%s" % (value, weekday_ja(day), status)
    when = parse_at(value).astimezone(tzinfo)
    return "%s（%s）%s・%s" % (day.isoformat(), weekday_ja(day), when.strftime("%H:%M"), status)


def chip_label(src, labels, tzinfo, year):
    if src["happened_at"] and src["happened_confirmed"]:
        day = local_date(src["happened_at"], tzinfo)
    else:
        day = local_date(src["captured_at"], tzinfo)
    date = ("%d/%d" % (day.month, day.day)) if day and day.year == year else (
        "%d/%d/%d" % (day.year, day.month, day.day) if day else "?")
    parts = [date, labels["source_kinds"].get(src["kind"], src["kind"])]
    if src["media_time"]:
        parts.append(src["media_time"])
    if src["page"]:
        parts.append("p.%d" % src["page"])
    return " ".join(parts)


def history_ja(state, line_id, labels, tzinfo):
    types = labels["types"]
    out, rev = [], 0
    for ev in history_entries(state, line_id):
        d, op = ev["data"], ev["op"]
        if op == "add_line":
            rev = 1
            what = "作成（%s）：「%s」 出典 %s" % (types.get(d["type"], d["type"]), d["text"],
                                           "・".join(c["source"] for c in d["cites"]))
        elif op == "revise_line":
            rev += 1
            parts = []
            if "text" in d:
                parts.append("本文「%s」" % d["text"])
            if "type" in d:
                parts.append("種類 %s" % types.get(d["type"], d["type"]))
            if "cites" in d:
                parts.append("出典 %s" % "・".join(c["source"] for c in d["cites"]))
            what = "修正（第%d版）：%s 理由：%s" % (rev, "、".join(parts), d.get("reason", ""))
        elif op == "promote":
            rev += 1
            if "evidence" in d:
                ev_src = d["evidence"]
                basis = "根拠 %s%s" % (ev_src["source"], ("「%s」" % ev_src["quote"]) if "quote" in ev_src else "")
            else:
                basis = "本人が確認"
            what = "昇格（第%d版）：%s → %s（%s）" % (rev, types["guess"], types.get(d["to"], d["to"]), basis)
        elif op == "approve":
            revs = [i["rev"] for i in d["lines"] if i["line"] == line_id]
            what = "承認（第%s版）" % (revs[0] if revs else "?")
        else:
            what = "メモ：%s" % d.get("text", "")
        out.append({"seq": ev["seq"], "op": op, "at": fmt_local(ev["at"], tzinfo),
                    "actor": "本人" if ev["actor"] == "her" else "Claude", "what": what})
    return out


def check_banner(led, state, tzinfo):
    last = led.read_last_check()
    if not last or "checked_at" not in last:
        return {"state": "none", "label": "チェック未実行", "detail": "", "stale": ""}
    when = fmt_local(last["checked_at"], tzinfo)
    if last.get("ok"):
        label, kind = "チェック：合格", "pass"
    else:
        label, kind = "チェック：不合格（エラー%d件）" % int(last.get("errors", 0)), "fail"
    detail = "（%s 実行" % when
    if last.get("warnings"):
        detail += "・注意%d件" % int(last["warnings"])
    if last.get("drafts"):
        detail += "・下書き%d行" % len(last["drafts"])
    detail += "）"
    stale = ""
    head, seen = state.head, last.get("head") or {}
    if seen.get("seq") != head["seq"] or seen.get("hash") != head["hash"]:
        if isinstance(seen.get("seq"), int) and seen["seq"] < head["seq"]:
            stale = "その後に%d件の変更（未チェック）" % (head["seq"] - seen["seq"])
        else:
            stale = "チェックの後に記録が変わりました（未チェック）"
    return {"state": kind, "label": label, "detail": detail, "stale": stale}


def build_view_model(state, led, tzinfo, now, doc_id=None, chain_broken=False):
    labels = PROFILES[state.meta["profile"]]
    year = now.year
    docs = [state.docs[doc_id]] if doc_id else list(state.docs.values())
    data_sources, data_lines, view_docs = {}, {}, []
    for doc in docs:
        vlines = []
        for lid in doc["lines"]:
            line = state.lines[lid]
            chips, cite_data = [], {}
            for c in line["cites"]:
                sid = c["source"]
                src = state.sources.get(sid)
                if src is None:
                    continue
                if sid not in cite_data:
                    label = chip_label(src, labels, tzinfo, year)
                    chips.append({"source": sid, "label": label})
                    cite_data[sid] = {"quotes": [], "spans": []}
                    if sid not in data_sources:
                        data_sources[sid] = {
                            "id": sid, "kind": src["kind"],
                            "kind_label": labels["source_kinds"].get(src["kind"], src["kind"]),
                            "speaker": src["speaker"], "text": src["text"],
                            "captured": fmt_local(src["captured_at"], tzinfo), "happened": fmt_happened(src, tzinfo),
                            "file": src["file"], "page": src["page"], "media_time": src["media_time"], "chip": label,
                        }
                if "quote" in c:
                    cite_data[sid]["quotes"].append(c["quote"])
                    span = quote_span(src["text"], c["quote"])
                    if span:
                        cite_data[sid]["spans"].append(list(span))
            data_lines[lid] = {
                "id": lid, "text": line["text"], "type": line["type"],
                "type_label": labels["types"][line["type"]], "status": line["status"], "rev": line["rev"],
                "cites": cite_data, "history": history_ja(state, lid, labels, tzinfo),
            }
            vlines.append({"id": lid, "type": line["type"], "type_label": labels["types"][line["type"]],
                           "status": line["status"], "status_label": "承認済み" if line["status"] == "approved" else "下書き",
                           "rev": line["rev"], "text": line["text"], "chips": chips})
        view_docs.append({"id": doc["id"], "title": doc["title"], "kind_label": labels["doc_kinds"].get(doc["kind"], doc["kind"]),
                          "for": doc.get("for"), "lines": vlines})
    if len(docs) == 1:
        title = docs[0]["title"]
    elif docs:
        title = "記録（%d件の文書）" % len(docs)
    else:
        title = "記録"
    offset = fmt_offset(now.utcoffset())
    return {
        "title": title,
        "sample": bool(state.meta.get("sample")),
        "check": check_banner(led, state, tzinfo),
        "chain_broken": chain_broken,
        "generated": now.strftime("%Y-%m-%d %H:%M"),
        "tz_label": "%s（%s）" % (state.meta["timezone"], offset),
        "legend": [{"type": t, "label": labels["types"][t], "help": labels["type_help"][t]} for t in TYPES],
        "docs": view_docs,
        "data": {"sources": data_sources, "lines": data_lines},
    }


# --------------------------------------------------------------------- CLI

def build_parser():
    parser = argparse.ArgumentParser(
        prog="ledger.py",
        description="kune-trace: a ledger where every line of a record cites its source. "
                    "Commands: init, now, add-source, add-doc, add-line, revise-line, promote, approve, note, "
                    "state, history, check, render.")
    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.required = True

    def cmd(name, func, help_text):
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.add_argument("--dir", default=DEFAULT_DIR, help="ledger folder (default: ./%s)" % DEFAULT_DIR)
        p.set_defaults(func=func)
        return p

    def actor(p):
        p.add_argument("--actor", choices=ACTORS, help="who made this change (her or claude)")

    p = cmd("init", cmd_init, "create a ledger folder: ledger.json, an empty log.jsonl and views/")
    p.add_argument("--profile", default=DEFAULT_PROFILE, help="label profile (default: %s)" % DEFAULT_PROFILE)
    p.add_argument("--tz", default=DEFAULT_TZ, help="IANA time zone or +09:00 offset (default: %s)" % DEFAULT_TZ)
    p.add_argument("--sample", action="store_true", help="mark the ledger as fictional sample data")

    p = cmd("now", cmd_now, "print the clock: UTC, local time, the date and the weekday in Japanese")
    p.add_argument("--tz", help="time zone to use instead of the ledger's")
    p.add_argument("--days", type=int, help="also print the local date N days away (-1 = the day before)")
    p.add_argument("--json", action="store_true")

    p = cmd("add-source", cmd_add_source, "record something she shared, verbatim")
    p.add_argument("--kind", required=True, choices=SOURCE_KINDS)
    p.add_argument("--text", help="the verbatim text (her words, or the transcription)")
    p.add_argument("--stdin", action="store_true", help="read the verbatim text from stdin (UTF-8)")
    p.add_argument("--speaker", help="who said or wrote it, if not her")
    p.add_argument("--file", help="the photo, recording or document file in her folder")
    p.add_argument("--page", type=int, help="page number in the document")
    p.add_argument("--media-time", dest="media_time", help="position in the recording, e.g. 0:14")
    p.add_argument("--happened-at", dest="happened_at", help="absolute ISO date/datetime when it happened")
    p.add_argument("--confirmed", action="store_true", help="she confirmed --happened-at (or it is printed on the document)")
    actor(p)

    p = cmd("add-doc", cmd_add_doc, "start a document: a visit memo, a record or a timeline")
    p.add_argument("--title", required=True)
    p.add_argument("--kind", required=True, choices=DOC_KINDS)
    p.add_argument("--for", dest="for_", help="who it is for, e.g. the doctor")
    actor(p)

    p = cmd("add-line", cmd_add_line, "add a line that cites its sources")
    p.add_argument("--doc", required=True)
    p.add_argument("--type", required=True, choices=TYPES)
    p.add_argument("--text", required=True)
    p.add_argument("--cite", action="append", default=[], metavar='S0003[:"quote"]',
                   help="a source id, optionally with a verbatim quote; repeat for more")
    actor(p)

    p = cmd("revise-line", cmd_revise_line, "change a line with a new event and a reason (it goes back to draft)")
    p.add_argument("--line", required=True)
    p.add_argument("--text")
    p.add_argument("--type", choices=TYPES)
    p.add_argument("--cite", action="append", default=[], metavar='S0003[:"quote"]',
                   help="replaces all cites; repeat for more")
    p.add_argument("--reason", required=True)
    actor(p)

    p = cmd("promote", cmd_promote, "turn a guess into another type, with evidence or her confirmation")
    p.add_argument("--line", required=True)
    p.add_argument("--to", required=True, choices=FACT_TYPES)
    basis = p.add_mutually_exclusive_group(required=True)
    basis.add_argument("--evidence", metavar='S0007[:"quote"]', help="the source that supports it")
    basis.add_argument("--confirmed-by-her", dest="confirmed_by_her", action="store_true")
    p.add_argument("--reason")
    actor(p)

    p = cmd("approve", cmd_approve, "record her approval of a line or of every draft line in a doc")
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--line")
    target.add_argument("--doc")
    actor(p)

    p = cmd("note", cmd_note, "add a note to the log; with --about S0001 --happened-at, set that source's date")
    p.add_argument("--text", required=True)
    p.add_argument("--about")
    p.add_argument("--happened-at", dest="happened_at")
    p.add_argument("--confirmed", action="store_true")
    actor(p)

    p = cmd("state", cmd_state, "print the current sources, docs and lines")
    p.add_argument("--json", action="store_true")

    p = cmd("history", cmd_history, "print every event of one line")
    p.add_argument("--line", required=True)

    p = cmd("check", cmd_check, "run every rule; exit 1 on any error")
    p.add_argument("--json", action="store_true")

    p = cmd("render", cmd_render, "write a static HTML view (views/index.html, or views/<doc>.html)")
    p.add_argument("--doc")
    p.add_argument("--out", help="output file")
    return parser


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    try:
        return args.func(args)
    except LedgerError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except (ValueError, OSError):
                pass


if __name__ == "__main__":
    _utf8_stdio()
    sys.exit(main())
