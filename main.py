"""
Entrypoint run by the GitHub Actions workflow on pull_request events.
Expects the repo to already be checked out at the PR's merge/head commit
(actions/checkout does this).

Required env vars:
  ANTHROPIC_API_KEY   - Claude API key
  GITHUB_TOKEN        - Actions-provided token (needs pull-requests: write)
  GITHUB_REPOSITORY   - auto-set by Actions, "owner/repo"
  PR_NUMBER           - set explicitly in the workflow from the event payload
  BASE_SHA, HEAD_SHA  - set explicitly in the workflow from the event payload
"""
import os
import sys

from agents import orchestrator
from tools.analysis_tools import get_diff_line_map, get_diff_summary
from tools.github_tools import GithubContext, post_review


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = int(os.environ["PR_NUMBER"])
    base_sha = os.environ["BASE_SHA"]
    head_sha = os.environ["HEAD_SHA"]
    token = os.environ["GITHUB_TOKEN"]

    print(f"[pr-security-agent] Reviewing {repo}#{pr_number} ({base_sha[:7]}...{head_sha[:7]})")

    diff_summary = get_diff_summary(base_sha, head_sha)
    if "Changed files (0)" in diff_summary or not diff_summary.strip():
        print("[pr-security-agent] No changed files detected, skipping.")
        return

    result = orchestrator.run(diff_summary, context={"base_sha": base_sha, "head_sha": head_sha})

    findings = result.get("findings", [])
    verdict = result.get("verdict", "comment")
    summary = result.get("summary", "Automated review completed.")

    print(f"[pr-security-agent] Verdict: {verdict} | {len(findings)} finding(s)")
    for f in findings:
        print(f"  - [{f.get('severity')}] {f.get('file')}:{f.get('line')} {f.get('title')}")

    ctx = GithubContext(token=token, repo=repo, pr_number=pr_number, head_sha=head_sha)

    header = f"## 🤖 Automated PR Review\n\n{summary}\n"
    valid_lines = get_diff_line_map(base_sha, head_sha)
    post_review(ctx, findings, verdict, header, valid_lines=valid_lines)

    if verdict == "request_changes":
        # Non-zero exit fails the Action job/check — useful if you wire this
        # up as a required status check to gate merges on critical/high findings.
        sys.exit(1)


if __name__ == "__main__":
    main()
