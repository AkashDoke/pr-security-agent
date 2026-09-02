"""
Test the agent locally against any two git refs in the current repo —
no GitHub API, no Actions, nothing gets posted anywhere. Just prints what
the orchestrator and its specialist agents would have found.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    cd /path/to/some/git/repo          # any repo — this one, or a real project
    python test_local.py                              # diffs HEAD~1 -> HEAD
    python test_local.py --base main --head my-branch  # diffs two branches
    python test_local.py --base abc123 --head def456   # diffs two commits
"""
import argparse
import json
import os
import sys

# Allow running this script with the target repo as the working directory
# (needed so git diff/grep/semgrep operate on the right repo) while still
# importing the agent package from wherever this file actually lives.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents import orchestrator
from tools.analysis_tools import get_diff_summary

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="HEAD~1", help="base git ref (default: HEAD~1)")
    parser.add_argument("--head", default="HEAD", help="head git ref (default: HEAD)")
    parser.add_argument("--json", action="store_true", help="print raw JSON result instead of formatted output")
    args = parser.parse_args()

    print(f"Diffing {args.base}...{args.head}\n")
    diff_summary = get_diff_summary(args.base, args.head)

    if "Changed files (0)" in diff_summary:
        print("No changed files between those refs. Nothing to review.")
        sys.exit(0)

    print(diff_summary[:800])
    print("...\n" if len(diff_summary) > 800 else "\n")
    print("Running orchestrator (this calls the Claude API — may take 30-90s)...\n")

    result = orchestrator.run(diff_summary, context={"base_sha": args.base, "head_sha": args.head})

    if args.json:
        print(json.dumps(result, indent=2))
        return

    findings = sorted(result.get("findings", []), key=lambda f: SEVERITY_ORDER.get(f.get("severity"), 9))
    verdict = result.get("verdict", "comment")
    summary = result.get("summary", "")

    print("=" * 70)
    print(f"VERDICT: {verdict.upper()}")
    print(f"SUMMARY: {summary}")
    print(f"FINDINGS: {len(findings)}")
    print("=" * 70)

    for f in findings:
        print(f"\n[{f.get('severity', '?').upper()}] {f.get('file')}:{f.get('line')} — {f.get('title')}")
        print(f"  {f.get('description', '')}")
        if f.get("suggested_fix"):
            print(f"  Suggested fix:\n    " + f["suggested_fix"].replace("\n", "\n    "))
        if f.get("agent"):
            print(f"  (flagged by: {f['agent']})")

    if not findings:
        print("\nNo findings.")


if __name__ == "__main__":
    main()
