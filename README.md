# continued-plugins

Small, standalone plugins for Claude Code and Codex, from the makers of [Continued](https://stagecontinuity.com).

| Plugin | What it does |
|---|---|
| [plan-chain](plugins/plan-chain) | Keep plan files in a chain and pick up the current plan instead of guessing. Say "continue" and the agent starts from the plan that superseded the others. |

## Install

Claude Code:

```
/plugin marketplace add StageContinuity/continued-plugins
/plugin install plan-chain@continued-plugins
```

Codex:

```
codex plugin marketplace add StageContinuity/continued-plugins
```

Each plugin works on its own, in any repository. [Continued](https://stagecontinuity.com) is a Mac app that runs Claude Code and Codex side by side, records which agent made each file, and hands work between sessions with the right plan.

Not affiliated with Anthropic or OpenAI.

## License

Apache-2.0. Issues and pull requests are welcome.
