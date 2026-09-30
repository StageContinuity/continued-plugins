# plan-chain

Say "continue" and your agent starts from the current plan, not an outdated one.

Repos collect plan files: `pagination-plan.md`, `pagination-plan-v2.md`, `page-size-plan.md`… An agent asked to "continue the plan" has to guess which one is current, and a wrong guess means implementing a fix you already rejected. plan-chain keeps a tiny front-matter block on each plan and follows the `supersedes` links to the one current plan:

```
$ python3 scripts/plan_chain.py current --topic pagination
"say": "Using page-boundary-plan.md · 4ae68249f07b (supersedes pagination-plan.md)"
```

When more than one plan could be current, it lists the candidates and the agent asks you, instead of guessing.

## What it does

| You say / do | The agent |
|---|---|
| "continue", "implement the plan", "繼續" | Runs `current`, opens the one current plan and tells you which plan it's using and what it replaced |
| Writes a new plan that replaces older ones | Runs `new … --supersedes old.md` so the old plans are marked `superseded` |
| Finishes a plan | Runs `done` |
| `/plan-chain:current-plan [topic]` (Claude Code) | Shows the current plan in one line |

A plan's front matter looks like this. Existing plans without it still work; a line like "Supersedes `old-plan.md`" near the top of a plan is also understood.

```yaml
---
title: Page boundary fix
status: active            # active | superseded | done
supersedes: [pagination-plan.md]
superseded_by:
author: claude-code
topic: pagination
updated: 2026-09-22
---
```

## Install

Claude Code:

```
/plugin marketplace add StageContinuity/continued-plugins
/plugin install plan-chain@continued-plugins
```

Codex:

```
codex plugin marketplace add StageContinuity/continued-plugins
codex plugin add plan-chain@continued-plugins
```

## Privacy and safety

- Standard-library Python 3, no dependencies, no network access.
- Reads and writes only Markdown files in your plan folders (`docs/plans`, `plans`, `.plans`, `docs/plan`, or `--dir`). It optionally runs `git log` on a plan file to show its last commit.
- Never deletes plans; superseded plans stay as history.

## Tests

```
python3 -m unittest discover -s plugins/plan-chain/tests
```

## From Continued

plan-chain is a small, standalone piece of [Continued](https://stagecontinuity.com), a Mac app for running Claude Code and Codex side by side. In Continued, "continue" also follows the chain of sessions and handoffs, and every file records which agent and session made it. plan-chain works on its own in any repo.

Not affiliated with Anthropic or OpenAI. Claude Code is a product of Anthropic; Codex is a product of OpenAI.

## License

Apache-2.0
