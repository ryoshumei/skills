# skills

ryoshumei's Claude Code plugins, in one marketplace named `ryoshumei`.

| Plugin | What it does | Where it lives |
|---|---|---|
| `naming-ja` | Names an app or product for Japan together with its owner. It asks about their taste first and generates a wide list across Japanese naming styles. The owner makes every cut. Every batch is screened against the Japanese App Store and same-reading trademarks before the owner sees it, and the finalists also get J-PlatPat, domain and meaning checks in Japanese, English and Chinese. | [`plugins/naming-ja`](plugins/naming-ja) |
| `implement-orchestrated` | An orchestrator-subagent `/implement` built on Matt Pocock's skills. It runs parallel coders in worktrees, reviews each ticket, and sends fixes back to the same coder. | [ryoshumei/implement-orchestrated](https://github.com/ryoshumei/implement-orchestrated) |

## Install

```bash
claude plugin marketplace add ryoshumei/skills
claude plugin install naming-ja@ryoshumei
claude plugin install implement-orchestrated@ryoshumei
```

Inside a session, `/plugin marketplace add ryoshumei/skills` and `/plugin install naming-ja@ryoshumei` do the same.

To turn a plugin on for everyone who works in a project, add this to the project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "ryoshumei": { "source": { "source": "github", "repo": "ryoshumei/skills" } }
  },
  "enabledPlugins": { "naming-ja@ryoshumei": true }
}
```

Cloud sessions, including Claude Code on the web, don't load the plugins that a repository's `.claude/settings.json` turns on ([docs](https://code.claude.com/docs/en/plugins/install)). For those sessions, copy the skill folder into the project instead, where it's part of the clone: `cp -r plugins/naming-ja/skills/naming-ja <project>/.claude/skills/`.

## Updates

```bash
claude plugin marketplace update ryoshumei
claude plugin update naming-ja@ryoshumei
```

Restart Claude Code afterwards. Each release bumps `version` in the plugin's `plugin.json`, and `claude plugin update` compares versions, so it says "already at the latest version" until a new one is published.

Auto-update is off by default for third-party marketplaces like this one. To turn it on, run `/plugin`, open the **Marketplaces** tab, select `ryoshumei`, and select **Enable auto-update**.

## Moving from ryoshumei/implement-orchestrated

The `ryoshumei` marketplace used to live in the implement-orchestrated repo. It still works there and still delivers implement-orchestrated updates, but it doesn't list naming-ja.

Claude Code keeps one marketplace per name, and it refuses to add `ryoshumei/skills` while `ryoshumei` still points at the old repo. To switch:

```bash
claude plugin marketplace remove ryoshumei
claude plugin marketplace add ryoshumei/skills
claude plugin install implement-orchestrated@ryoshumei
claude plugin install naming-ja@ryoshumei
```

Removing the old marketplace uninstalls its plugins and deletes their saved options, so the first `install` puts implement-orchestrated back.

## What naming-ja needs

- Claude Code with the AskUserQuestion tool; subagents are optional.
- Node 20 or later for the two scripts in `scripts/`. They have no dependencies:
  - `check-names.mjs` searches the Japanese App Store (iTunes Search API) and checks domains over RDAP. With `--tm`, it also reads same-reading JPO trademarks from patent-i.com at the 5-second interval its robots.txt asks for.
  - `seen-check.mjs` flags names that repeat or nearly repeat names from earlier rounds.
- Its checks are a first screen, not legal clearance. Before you spend money on a name, have a patent attorney (弁理士) clear it.

## Layout

```text
.claude-plugin/marketplace.json                the plugin list
plugins/<plugin>/.claude-plugin/plugin.json    a plugin kept in this repo
plugins/<plugin>/skills/<skill>/SKILL.md       its skill, with references/ and scripts/ beside it
```

A plugin can also live in its own repo, like implement-orchestrated, and be listed here with a `github` source.

## License and credits

MIT, see [LICENSE](LICENSE). The four-step structure of `naming-ja` is adapted from arn-spark-naming (AppsVortex/arness, MIT License); see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
