---
description: Show the current plan in this repo's plan chain (and what it replaced)
argument-hint: "[topic]"
---

Use the plan-chain skill. Run its `current` command from the repository root, passing `--topic "$ARGUMENTS"` when a topic was given. Report the plan name, hash and what it supersedes in one line. If the result is ambiguous, list the candidates (newest first) and ask which one is current; do not choose for the user.
