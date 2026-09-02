#!/usr/bin/env python3
"""
Review a real GitHub PR from your local machine — fetches PR metadata via
the GitHub API, pulls the relevant commits, runs the orchestrator, and posts
the review back to the actual PR. No GitHub Actions involved.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    export GITHUB_TOKEN=ghp_...          # needs repo scope / pull-requests write
    cd /path/to/your/local/clone of the target repo

    python review_pr.py 42                    # review PR #42 (repo auto-detected from origin)
    python review_pr.py 42 --repo owner/name   # explicit repo
    python review_pr.py 42 --dry-run           # print findings, don't post anything
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents import orchestrator
from tools.analysis_tools import get_diff_summary
from tools.github_tools import GithubContext, get_pr, post_review


def infer_repo() -> str:
    url = subprocess.run(
        ["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=True
    ).stdout.strip()
    url = url.replace("git@github.com:", "").replace("https://github.com/", "")
    return url[:-4] if url.endswith(".git") else url


def get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    print("ERROR: set GITHUB_TOKEN, or run `gh auth login` (uses the gh CLI's token as a fallback).", file=sys.stderr)
    sys.exit(1)


def review_pr(repo: str, pr_number: int, token: str, dry_run: bool = False) -> dict:
    print(f"Fetching PR #{pr_number} metadata for {repo}...")
    pr = get_pr(repo, pr_number, token)
    base_sha, head_sha = pr["base"]["sha"], pr["head"]["sha"]
    print(f"  base={base_sha[:7]} head={head_sha[:7]}  \"{pr['title']}\"")

    print("Fetching latest refs from origin...")
    subprocess.run(["git", "fetch", "origin", "+refs/heads/*:refs/remotes/origin/*", "--prune"], check=True)

    diff_summary = get_diff_summary(base_sha, head_sha)
    if "Changed files (0)" in diff_summary:
        print("No changed files. Nothing to review.")
        return {"findings": [], "verdict": "approve", "summary": "No changes."}

    print("Running orchestrator (calls Claude API, may take 30-90s)...\n")
    result = orchestrator.run(diff_summary, context={"base_sha": base_sha, "head_sha": head_sha})

    findings = result.get("findings", [])
    verdict = result.get("verdict", "comment")
    summary = result.get("summary", "")

    print("=" * 70)
    print(f"VERDICT: {verdict.upper()}  |  {len(findings)} finding(s)")
    print(summary)
    print("=" * 70)
    for f in findings:
        print(f"[{f.get('severity')}] {f.get('file')}:{f.get('line')} — {f.get('title')}")

    if dry_run:
        print("\n--dry-run set: not posting to GitHub.")
        return result

    ctx = GithubContext(token=token, repo=repo, pr_number=pr_number, head_sha=head_sha)
    header = f"## 🤖 Automated PR Review (run locally)\n\n{summary}\n"
    post_review(ctx, findings, verdict, header)
    print(f"\nPosted review to {repo}#{pr_number}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pr_number", type=int)
    parser.add_argument("--repo", help="owner/name (auto-detected from git remote 'origin' if omitted)")
    parser.add_argument("--dry-run", action="store_true", help="print findings, don't post to GitHub")
    args = parser.parse_args()

    repo = args.repo or infer_repo()
    token = get_token()
    review_pr(repo, args.pr_number, token, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
