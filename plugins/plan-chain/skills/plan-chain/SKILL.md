---
name: plan-chain
description: Keep a repository's plan files in a chain and pick up the current plan instead of guessing. Use when the user says "continue", "pick up the plan", "繼續", "which plan is current", asks you to implement "the plan", or when you write a new plan that replaces an older one. Works in any repo with a docs/plans (or plans/) folder, in Claude Code and Codex.
---

# Plan chain

Repos collect many plan files. Agents that guess which one is current often implement an outdated plan. This skill keeps a small front-matter block on each plan and follows the "supersedes" links to find the one current plan.

The helper is `scripts/plan_chain.py` next to this file. Run it with `python3`, from the repository root (or pass `--root`). It uses only the Python standard library, never touches the network, and only reads and writes files in the plan folders (`docs/plans`, `plans`, `.plans` or `docs/plan`, or any `--dir` you pass). Every command prints JSON.

## When the user asks you to continue or implement "the plan"

1. Run `python3 <this-skill>/scripts/plan_chain.py current` (add `--topic "<a short literal subject>"` when the user named one, e.g. `--topic pagination`).
2. Read the result:
   - `"result": "current"`: open `plan.path` and start from it. Say the `say` line to the user once, e.g. "Using page-boundary-plan.md · 4ae68249f07b (supersedes pagination-plan.md)". If `confidence` is `only-plan`, mention that the plan has no chain metadata yet.
   - `"result": "ambiguous"` (exit code 2): do not pick one. Ask the user one short question listing the candidate names (newest first). After they answer, record the decision with `supersede` or `done` so the next session does not have to ask.
   - `"result": "none"`: ask which plan to use, or offer to start a new one.
3. Before editing code against a plan, re-read the plan file; if its `hash` changed since you resolved it, re-read and reconcile.

## When you write a plan

- New plan that replaces older ones: `plan_chain.py new docs/plans/<name>.md --title "<title>" --supersedes old-a.md,old-b.md --author <your agent name, e.g. claude-code or codex> --topic <short topic>`. This creates the file with front matter (or adds front matter to an existing file) and marks each old plan `status: superseded` with `superseded_by`. Then write the plan body.
- A plan you just learned is replaced: `plan_chain.py supersede <old>.md --by <new>.md`.
- A plan that is fully implemented: `plan_chain.py done <plan>.md`.
- Existing plans without metadata are fine. The helper also reads a line like "Supersedes `old-plan.md`" near the top of a plan body.

## Housekeeping

- `plan_chain.py status` lists active, unmarked, superseded and done plans.
- `plan_chain.py check` reports missing links, cycles and several active plans on the same topic. Offer fixes; do not rewrite plans the user did not ask about.

## Boundaries

- Never delete plans. Superseded plans stay as history.
- Do not invent chain links. Link plans only when the user or a plan's own text says one replaces another.
- Front matter edits keep the plan body unchanged.
