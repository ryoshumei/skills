"""Packaging: SKILL.md frontmatter, plugin.json, Python 3.9 syntax, and the real CLI process."""

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import pathlib
import shutil
import unittest

from support import SKILL_DIR, SCRIPTS_DIR, EXAMPLES_DIR

PLUGIN_DIR = SKILL_DIR.parents[1]


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise AssertionError("SKILL.md has no frontmatter")
    fields = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = json.loads(value)
        fields[key.strip()] = value
    return fields


class SkillMdTest(unittest.TestCase):

    def setUp(self):
        self.text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.fm = frontmatter(self.text)

    def test_name(self):
        name = self.fm["name"]
        self.assertEqual(name, "kune-trace")
        self.assertRegex(name, r"^[a-z0-9-]{1,64}$")
        self.assertNotIn("claude", name)
        self.assertNotIn("anthropic", name)

    def test_description(self):
        d = self.fm["description"]
        self.assertTrue(0 < len(d) <= 1024, len(d))
        self.assertNotRegex(d, r"[<>]")
        self.assertNotRegex(d.lower(), r"diagnos|cure|treat|triage|symptom checker|診断|治療|治る|病名")
        for trigger in ("memo", "where", "timeline", "correct"):
            self.assertIn(trigger, d.lower())

    def test_only_name_and_description(self):
        self.assertEqual(set(self.fm), {"name", "description"})

    def test_body_covers_the_brief(self):
        for phrase in ("emergency", "other_ai", "ledger.py now", "check", "render", "promote", "approve",
                       "Claude desktop", "Claude Code", "claude.ai", "Privacy", "Out of scope"):
            self.assertIn(phrase, self.text)

    def test_linked_references_exist(self):
        for rel in re.findall(r"\]\(((?:references|examples)/[^)#]+)\)", self.text):
            self.assertTrue((SKILL_DIR / rel).exists(), rel)
        for name in ("ledger-format.md", "claim-types.md", "time.md"):
            self.assertTrue((SKILL_DIR / "references" / name).exists(), name)


class PluginJsonTest(unittest.TestCase):

    def test_plugin_json(self):
        manifest = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
        if not manifest.exists():
            self.skipTest("the skill runs outside its plugin (for example, uploaded as a zip)")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "kune-trace")
        self.assertEqual(data["version"], "0.0.1")
        self.assertEqual(data["skills"], ["./skills/kune-trace"])
        self.assertEqual(data["license"], "MIT")
        for key in ("author", "homepage", "repository", "description"):
            self.assertIn(key, data)
        self.assertTrue((PLUGIN_DIR / "README.md").exists())


class Python39SyntaxTest(unittest.TestCase):

    def test_sources_parse_as_python_3_9(self):
        files = sorted(SCRIPTS_DIR.glob("*.py")) + sorted(EXAMPLES_DIR.glob("*.py")) + sorted(SKILL_DIR.glob("tests/*.py"))
        self.assertTrue(files)
        for path in files:
            with self.subTest(file=path.name):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 9))

    def test_no_newer_stdlib_apis(self):
        newer = re.compile(r"datetime\.UTC\b|\bstrict=True|itertools\.pairwise|\btomllib\b|StrEnum|\bmatch \w+:\s*$"
                           r"|ExceptionGroup|slots=True|kw_only=True", re.M)
        for path in sorted(SCRIPTS_DIR.glob("*.py")) + sorted(EXAMPLES_DIR.glob("*.py")):
            with self.subTest(file=path.name):
                self.assertIsNone(newer.search(path.read_text(encoding="utf-8")))

    def test_no_network_modules(self):
        net = re.compile(r"^\s*(?:import|from)\s+(?:urllib|http|socket|ssl|requests|ftplib|smtplib|asyncio)\b", re.M)
        for path in sorted(SCRIPTS_DIR.glob("*.py")) + sorted(EXAMPLES_DIR.glob("*.py")):
            with self.subTest(file=path.name):
                self.assertIsNone(net.search(path.read_text(encoding="utf-8")))


class RealProcessTest(unittest.TestCase):
    """The script as Claude runs it: a separate process, whatever the console encoding."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="kune-trace-proc-"))

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def call(self, *argv, stdin=None, env_extra=None):
        env = dict(os.environ)
        env.update(env_extra or {})
        return subprocess.run([sys.executable, str(SCRIPTS_DIR / "ledger.py")] + [str(a) for a in argv],
                              input=stdin, capture_output=True, env=env, cwd=str(self.tmp))

    def test_help(self):
        p = self.call("--help")
        self.assertEqual(p.returncode, 0, p.stderr)
        for cmd in ("init", "now", "add-source", "add-doc", "add-line", "revise-line", "promote", "approve",
                    "state", "history", "check", "render"):
            self.assertIn(cmd, p.stdout.decode("utf-8"))

    def test_utf8_output_even_with_a_legacy_console_encoding(self):
        env = {"PYTHONIOENCODING": "ascii"}
        self.assertEqual(self.call("init", env_extra=env).returncode, 0)
        p = self.call("add-source", "--kind", "chat", "--text", "頬のあたりが重い", env_extra=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        p = self.call("state", env_extra=env)
        self.assertIn("頬のあたりが重い", p.stdout.decode("utf-8"))

    def test_stdin_is_read_as_utf8_and_bom_is_dropped(self):
        self.assertEqual(self.call("init").returncode, 0)
        text = "みなと調剤薬局\r\nカルボシステイン錠500mg「JG」\r\n"
        p = self.call("add-source", "--kind", "photo", "--stdin", stdin=b"\xef\xbb\xbf" + text.encode("utf-8"),
                      env_extra={"PYTHONIOENCODING": "ascii"})
        self.assertEqual(p.returncode, 0, p.stderr)
        line = (self.tmp / "kune-ledger" / "log.jsonl").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(json.loads(line)["data"]["text"], "みなと調剤薬局\nカルボシステイン錠500mg「JG」")

    def test_default_folder_is_kune_ledger_in_the_working_directory(self):
        p = self.call("init")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.tmp / "kune-ledger" / "ledger.json").exists())
        self.assertTrue((self.tmp / "kune-ledger" / "log.jsonl").exists())

    def test_usage_error_exit_code(self):
        p = self.call("add-source", "--kind", "telepathy", "--text", "x")
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
