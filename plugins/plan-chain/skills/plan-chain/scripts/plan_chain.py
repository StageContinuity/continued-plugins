#!/usr/bin/env python3
"""plan-chain: keep a repo's plan files in a chain, and find the current plan.

Every plan is a Markdown file with a small front-matter block:

    ---
    title: Page boundary fix
    status: active            # active | superseded | done
    supersedes: [pagination-plan.md]
    superseded_by:
    author: claude-code       # the agent (or person) that wrote it
    updated: 2026-09-22
    ---

The chain is the set of "supersedes" links. The current plan is an active plan
that nothing supersedes. When more than one plan could be current, this tool
says so and lists the candidates instead of guessing.

Standard library only. No network access. It only reads and writes files inside
the plan folders you point it at.

Usage:
    plan_chain.py status  [--dir DIR]
    plan_chain.py current [--topic TEXT] [--dir DIR]
    plan_chain.py new PATH --title TEXT [--supersedes A.md,B.md] [--author NAME] [--topic TEXT]
    plan_chain.py supersede OLD --by NEW
    plan_chain.py done PATH
    plan_chain.py check [--dir DIR]

All commands print JSON on stdout. Exit code 0 = ok, 1 = error, 2 = needs a
decision (for example several candidate plans).
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

DEFAULT_DIRS = ("docs/plans", "plans", ".plans", "docs/plan")
KEYS = ("title", "status", "supersedes", "superseded_by", "author", "topic", "updated")
STATUSES = ("active", "superseded", "done")
SUPERSEDES_LINE = re.compile(r"^\s*(?:\*\*)?supersedes(?:\*\*)?\s*[:：]?\s*(.+)$", re.I)
MD_NAME = re.compile(r"[`\[(]?([\w.\-/]+\.md)[`\])]?", re.I)


# ---------------------------------------------------------------- front matter

def split_front_matter(text):
    """Return (meta dict, body, had_front_matter)."""
    if not text.startswith("---"):
        return {}, text, False
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text, False
    meta, key = {}, None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, "".join(lines[i + 1:]), True
        item = re.match(r"^\s*-\s+(.*)$", line)
        if item and key:
            meta.setdefault(key, [])
            if not isinstance(meta[key], list):
                meta[key] = [meta[key]] if meta[key] else []
            meta[key].append(_scalar(item.group(1)))
            continue
        pair = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if pair:
            key = pair.group(1).lower()
            meta[key] = _value(pair.group(2))
    return {}, text, False  # unterminated block: treat as no front matter


def _scalar(raw):
    raw = raw.split(" #", 1)[0].strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1]
    return raw


def _value(raw):
    raw = raw.split(" #", 1)[0].strip()
    if raw.startswith("[") and raw.endswith("]"):
        return [_scalar(x) for x in raw[1:-1].split(",") if x.strip()]
    return _scalar(raw)


def _as_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return [v for v in value if v]
    return [v.strip() for v in str(value).split(",") if v.strip()]


def render_front_matter(meta):
    out = ["---"]
    for key in KEYS + tuple(k for k in meta if k not in KEYS):
        if key not in meta:
            continue
        value = meta[key]
        if isinstance(value, list):
            out.append(f"{key}: [{', '.join(value)}]")
        else:
            out.append(f"{key}: {value}" if value not in (None, "") else f"{key}:")
    out.append("---")
    return "\n".join(out) + "\n"


def write_meta(path, updates):
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    meta, body, had = split_front_matter(text)
    meta.update(updates)
    body = body if had else text
    if body and not body.startswith("\n"):
        body = "\n" + body
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(render_front_matter(meta) + body)


# ---------------------------------------------------------------- discovery

def plan_dirs(root, explicit):
    if explicit:
        return [os.path.abspath(os.path.join(root, d)) for d in explicit]
    env = os.environ.get("PLAN_CHAIN_DIR")
    if env:
        return [os.path.abspath(os.path.join(root, d)) for d in env.split(os.pathsep) if d]
    return [os.path.abspath(os.path.join(root, d)) for d in DEFAULT_DIRS
            if os.path.isdir(os.path.join(root, d))]


def git_last_change(path):
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%an%x09%aI", "--", path],
                             cwd=os.path.dirname(path) or ".", capture_output=True,
                             text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            who, when = out.stdout.strip().split("\t", 1)
            return {"committer": who, "committed": when}
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


def load_plans(dirs):
    plans = {}
    for directory in dirs:
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if not name.lower().endswith(".md") or name.lower() in ("readme.md", "index.md"):
                continue
            path = os.path.join(directory, name)
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            meta, body, had = split_front_matter(text)
            inferred = []
            if not _as_list(meta.get("supersedes")):
                for line in body.splitlines()[:60]:
                    match = SUPERSEDES_LINE.match(line)
                    if match:
                        inferred += [os.path.basename(m) for m in MD_NAME.findall(match.group(1))]
            title = meta.get("title") or next(
                (l.lstrip("# ").strip() for l in body.splitlines() if l.startswith("#")), name)
            plans[name] = {
                "name": name,
                "path": path,
                "title": title,
                "marked": had and bool(meta.get("status")),
                "status": (meta.get("status") or "").lower() or None,
                "supersedes": [os.path.basename(x) for x in _as_list(meta.get("supersedes"))],
                "supersedes_inferred": [x for x in inferred if x != name],
                "superseded_by": [os.path.basename(x) for x in _as_list(meta.get("superseded_by"))],
                "author": meta.get("author"),
                "topic": meta.get("topic"),
                "updated": meta.get("updated"),
                "hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
            }
    return plans


# ---------------------------------------------------------------- chain logic

def build_chain(plans):
    """Return {name: set(names it supersedes)} using declared and inferred links."""
    edges = {name: set() for name in plans}
    for name, plan in plans.items():
        for old in plan["supersedes"] + plan["supersedes_inferred"]:
            if old in plans:
                edges[name].add(old)
        for new in plan["superseded_by"]:
            if new in plans:
                edges[new].add(name)
    return edges


def classify(plans, edges):
    superseded = {old for olds in edges.values() for old in olds}
    for name, plan in plans.items():
        if plan["status"] in ("done", "archived"):
            plan["state"] = "done"
        elif plan["status"] == "superseded" or name in superseded:
            plan["state"] = "superseded"
        elif plan["marked"] or edges[name]:
            plan["state"] = "active"
        else:
            plan["state"] = "unmarked"
    return plans


def lineage(name, edges, seen=None):
    """Names this plan replaced, newest first (breadth-first)."""
    seen = {name} if seen is None else seen
    order, frontier = [], [name]
    while frontier:
        nxt = []
        for current in frontier:
            for old in sorted(edges.get(current, ())):
                if old not in seen:
                    seen.add(old)
                    order.append(old)
                    nxt.append(old)
        frontier = nxt
    return order


def in_cycle(name, edges):
    """True when following "supersedes" links from this plan leads back to it."""
    stack, seen = list(edges.get(name, ())), set()
    while stack:
        current = stack.pop()
        if current == name:
            return True
        if current not in seen:
            seen.add(current)
            stack.extend(edges.get(current, ()))
    return False


def topic_match(plan, topic, edges=None):
    words = [w for w in re.split(r"[\s,/_\-]+", topic.lower()) if len(w) > 1]
    replaced = " ".join(lineage(plan["name"], edges)) if edges else ""
    haystack = " ".join(str(x or "") for x in (plan["name"], plan["title"], plan["topic"], replaced)).lower()
    return all(w in haystack for w in words) if words else True


def describe(plan, edges, plans):
    info = {k: plan[k] for k in ("name", "path", "title", "state", "author", "updated", "hash")}
    info["replaces"] = lineage(plan["name"], edges)
    info["git"] = git_last_change(plan["path"])
    return info


# ---------------------------------------------------------------- commands

def cmd_status(args):
    dirs = plan_dirs(args.root, args.dir)
    plans = load_plans(dirs)
    edges = build_chain(plans)
    classify(plans, edges)
    groups = {s: sorted(n for n, p in plans.items() if p["state"] == s)
              for s in ("active", "unmarked", "superseded", "done")}
    return 0, {"dirs": dirs, "count": len(plans), **groups}


def cmd_current(args):
    dirs = plan_dirs(args.root, args.dir)
    if not dirs:
        return 1, {"error": "No plan folder found. Pass --dir or create docs/plans/."}
    plans = load_plans(dirs)
    edges = build_chain(plans)
    classify(plans, edges)
    pool = [p for p in plans.values() if p["state"] == "active"]
    unmarked = [p for p in plans.values() if p["state"] == "unmarked"]
    if args.topic:
        pool = [p for p in pool if topic_match(p, args.topic, edges)]
        unmarked = [p for p in unmarked if topic_match(p, args.topic)]
    if len(pool) == 1:
        plan = describe(pool[0], edges, plans)
        note = f"Using {plan['name']} · {plan['hash']}"
        if plan["replaces"]:
            note += f" (supersedes {', '.join(plan['replaces'])})"
        return 0, {"result": "current", "plan": plan, "say": note,
                   "also_unmarked": [p["name"] for p in unmarked]}
    if not pool and len(unmarked) == 1:
        plan = describe(unmarked[0], edges, plans)
        return 0, {"result": "current", "plan": plan, "confidence": "only-plan",
                   "say": f"Using {plan['name']} · {plan['hash']} (the only plan that matches; it has no chain metadata yet)"}
    candidates = [describe(p, edges, plans) for p in (pool or unmarked)]
    candidates.sort(key=lambda c: str(c.get("updated") or (c["git"] or {}).get("committed") or ""), reverse=True)
    if not candidates:
        return 2, {"result": "none", "message": "No plan matches. Ask which plan to use, or start a new one.",
                   "all": sorted(plans)}
    return 2, {"result": "ambiguous",
               "message": "More than one plan could be current. Ask the user which one, then mark the others with `supersede` or `done`.",
               "candidates": candidates}


def _resolve_path(root, dirs, value):
    if os.path.isabs(value) or os.path.exists(os.path.join(root, value)):
        return os.path.abspath(os.path.join(root, value))
    for directory in dirs:
        candidate = os.path.join(directory, os.path.basename(value))
        if os.path.exists(candidate):
            return candidate
    return os.path.abspath(os.path.join(root, value))


def cmd_new(args):
    dirs = plan_dirs(args.root, args.dir) or [os.path.join(args.root, "docs/plans")]
    path = args.path
    if os.path.dirname(path) == "":
        path = os.path.join(dirs[0], path)
    path = os.path.abspath(os.path.join(args.root, path))
    today = datetime.date.today().isoformat()
    olds = [os.path.basename(x) for x in _as_list(args.supersedes)]
    for old in olds:
        old_path = _resolve_path(args.root, dirs, old)
        if not os.path.exists(old_path):
            return 1, {"error": f"{old} not found in the plan folders"}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"# {args.title}\n")
    write_meta(path, {"title": args.title, "status": "active", "supersedes": olds,
                      "author": args.author or "", "topic": args.topic or "", "updated": today})
    for old in olds:
        write_meta(_resolve_path(args.root, dirs, old),
                   {"status": "superseded", "superseded_by": [os.path.basename(path)], "updated": today})
    return 0, {"result": "created", "path": path, "supersedes": olds}


def cmd_supersede(args):
    dirs = plan_dirs(args.root, args.dir) or [args.root]
    old, new = _resolve_path(args.root, dirs, args.old), _resolve_path(args.root, dirs, args.by)
    for path in (old, new):
        if not os.path.exists(path):
            return 1, {"error": f"{path} not found"}
    today = datetime.date.today().isoformat()
    with open(new, encoding="utf-8") as handle:
        meta, _, _ = split_front_matter(handle.read())
    olds = _as_list(meta.get("supersedes"))
    if os.path.basename(old) not in olds:
        olds.append(os.path.basename(old))
    write_meta(new, {"status": meta.get("status") or "active", "supersedes": olds, "updated": today})
    write_meta(old, {"status": "superseded", "superseded_by": [os.path.basename(new)], "updated": today})
    return 0, {"result": "linked", "old": old, "new": new}


def cmd_done(args):
    dirs = plan_dirs(args.root, args.dir) or [args.root]
    path = _resolve_path(args.root, dirs, args.path)
    if not os.path.exists(path):
        return 1, {"error": f"{path} not found"}
    write_meta(path, {"status": "done", "updated": datetime.date.today().isoformat()})
    return 0, {"result": "done", "path": path}


def cmd_check(args):
    dirs = plan_dirs(args.root, args.dir)
    plans = load_plans(dirs)
    edges = build_chain(plans)
    classify(plans, edges)
    problems = []
    for name, plan in plans.items():
        for ref in plan["supersedes"] + plan["superseded_by"]:
            if ref not in plans:
                problems.append({"plan": name, "problem": f"refers to missing {ref}"})
        if plan["status"] and plan["status"] not in STATUSES + ("archived",):
            problems.append({"plan": name, "problem": f"unknown status '{plan['status']}'"})
        if in_cycle(name, edges):
            problems.append({"plan": name, "problem": "supersedes itself through a cycle"})
    active = [n for n, p in plans.items() if p["state"] == "active"]
    by_topic = {}
    for name in active:
        by_topic.setdefault((plans[name]["topic"] or "").lower(), []).append(name)
    for topic, names in by_topic.items():
        if topic and len(names) > 1:
            problems.append({"topic": topic, "problem": f"{len(names)} active plans: {', '.join(sorted(names))}"})
    unmarked = sorted(n for n, p in plans.items() if p["state"] == "unmarked")
    return (0 if not problems else 2), {"problems": problems, "unmarked": unmarked, "active": sorted(active)}


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=os.getcwd(), help="Repository root (default: current folder)")
    common.add_argument("--dir", action="append", help="Plan folder relative to root (repeatable)")
    parser = argparse.ArgumentParser(description="Keep plan files in a chain and find the current one.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", parents=[common])
    p = sub.add_parser("current", parents=[common]); p.add_argument("--topic", default="")
    p = sub.add_parser("new", parents=[common]); p.add_argument("path"); p.add_argument("--title", required=True)
    p.add_argument("--supersedes", default=""); p.add_argument("--author", default=""); p.add_argument("--topic", default="")
    p = sub.add_parser("supersede", parents=[common]); p.add_argument("old"); p.add_argument("--by", required=True)
    p = sub.add_parser("done", parents=[common]); p.add_argument("path")
    sub.add_parser("check", parents=[common])
    args = parser.parse_args(argv)
    args.root = os.path.abspath(args.root)
    handler = {"status": cmd_status, "current": cmd_current, "new": cmd_new,
               "supersede": cmd_supersede, "done": cmd_done, "check": cmd_check}[args.command]
    try:
        code, result = handler(args)
    except (OSError, ValueError) as error:
        code, result = 1, {"error": str(error)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
