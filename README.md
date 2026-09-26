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

- This marketplace lists every plugin. Claude Code keeps one marketplace per name, so adding another source named `ryoshumei` later replaces this one.
- Our Claude Code on the web session didn't install plugins from git URLs or from extra marketplaces. For web sessions, copy the skill folder into the project's `.claude/skills/` instead, for example `cp -r plugins/naming-ja/skills/naming-ja <project>/.claude/skills/`.

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
