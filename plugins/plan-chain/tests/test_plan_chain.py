"""Tests for plan_chain.py. Run: python3 -m unittest discover -s plugins/plan-chain/tests"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "skills", "plan-chain", "scripts"))
import plan_chain  # noqa: E402


def run(root, *argv):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = plan_chain.main(list(argv[:1]) + ["--root", root] + list(argv[1:]))
    return code, json.loads(buffer.getvalue())


def write(root, name, text):
    path = os.path.join(root, "docs", "plans", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


class PlanChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_plan_supersedes_old_and_becomes_current(self):
        write(self.root, "pagination-plan.md", "# Pagination plan\n\nZero-based pages.\n")
        code, out = run(self.root, "new", "page-boundary-plan.md", "--title", "Page boundary fix",
                        "--supersedes", "pagination-plan.md", "--author", "claude-code")
        self.assertEqual(code, 0, out)
        code, out = run(self.root, "current")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["plan"]["name"], "page-boundary-plan.md")
        self.assertEqual(out["plan"]["replaces"], ["pagination-plan.md"])
        self.assertEqual(out["plan"]["author"], "claude-code")
        self.assertIn("supersedes pagination-plan.md", out["say"])
        with open(os.path.join(self.root, "docs/plans/pagination-plan.md"), encoding="utf-8") as handle:
            old = handle.read()
        self.assertIn("status: superseded", old)
        self.assertIn("superseded_by: [page-boundary-plan.md]", old)
        self.assertIn("Zero-based pages.", old)  # body preserved

    def test_chain_of_three_reports_full_lineage(self):
        write(self.root, "a.md", "# A\n")
        run(self.root, "new", "b.md", "--title", "B", "--supersedes", "a.md")
        run(self.root, "new", "c.md", "--title", "C", "--supersedes", "b.md")
        code, out = run(self.root, "current")
        self.assertEqual(out["plan"]["name"], "c.md")
        self.assertEqual(out["plan"]["replaces"], ["b.md", "a.md"])

    def test_two_active_plans_are_ambiguous_not_guessed(self):
        write(self.root, "x.md", "---\ntitle: X\nstatus: active\n---\n# X\n")
        write(self.root, "y.md", "---\ntitle: Y\nstatus: active\n---\n# Y\n")
        code, out = run(self.root, "current")
        self.assertEqual(code, 2)
        self.assertEqual(out["result"], "ambiguous")
        self.assertEqual({c["name"] for c in out["candidates"]}, {"x.md", "y.md"})

    def test_topic_matches_replaced_plan_names(self):
        write(self.root, "pagination-plan.md", "# Pagination\n")
        write(self.root, "caching-plan.md", "---\ntitle: Caching\nstatus: active\n---\n")
        run(self.root, "new", "page-boundary-plan.md", "--title", "Page boundary",
            "--supersedes", "pagination-plan.md")
        code, out = run(self.root, "current", "--topic", "pagination")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["plan"]["name"], "page-boundary-plan.md")

    def test_supersedes_line_in_body_is_inferred(self):
        write(self.root, "old-plan.md", "# Old\n")
        write(self.root, "new-plan.md", "# New plan\n\nSupersedes `old-plan.md` (wrong diagnosis).\n")
        code, out = run(self.root, "current")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["plan"]["name"], "new-plan.md")
        code, out = run(self.root, "status")
        self.assertIn("old-plan.md", out["superseded"])

    def test_unmarked_plans_only_are_listed_when_more_than_one(self):
        write(self.root, "one.md", "# One\n")
        write(self.root, "two.md", "# Two\n")
        code, out = run(self.root, "current")
        self.assertEqual(code, 2)
        self.assertEqual(len(out["candidates"]), 2)

    def test_single_unmarked_plan_is_used_with_note(self):
        write(self.root, "only.md", "# Only\n")
        code, out = run(self.root, "current")
        self.assertEqual(code, 0)
        self.assertEqual(out["confidence"], "only-plan")

    def test_done_removes_from_candidates(self):
        write(self.root, "x.md", "---\nstatus: active\n---\n")
        write(self.root, "y.md", "---\nstatus: active\n---\n")
        run(self.root, "done", "x.md")
        code, out = run(self.root, "current")
        self.assertEqual(out["plan"]["name"], "y.md")

    def test_check_reports_cycles_and_missing_links(self):
        write(self.root, "a.md", "---\nstatus: active\nsupersedes: [b.md]\n---\n")
        write(self.root, "b.md", "---\nstatus: active\nsupersedes: [a.md, ghost.md]\n---\n")
        code, out = run(self.root, "check")
        self.assertEqual(code, 2)
        problems = " ".join(p["problem"] for p in out["problems"])
        self.assertIn("missing ghost.md", problems)
        self.assertIn("cycle", problems)

    def test_missing_plan_folder_is_an_error(self):
        code, out = run(self.root, "current")
        self.assertEqual(code, 1)
        self.assertIn("No plan folder", out["error"])

    def test_supersede_links_existing_files(self):
        write(self.root, "v1.md", "# v1\n")
        write(self.root, "v2.md", "# v2\n")
        code, out = run(self.root, "supersede", "v1.md", "--by", "v2.md")
        self.assertEqual(code, 0, out)
        code, out = run(self.root, "current")
        self.assertEqual(out["plan"]["name"], "v2.md")


if __name__ == "__main__":
    unittest.main()
