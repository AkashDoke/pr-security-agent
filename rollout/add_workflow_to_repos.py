#!/usr/bin/env python3
"""
Adds (or updates) .github/workflows/pr-review.yml — the thin stub that calls
the reusable workflow — in every repo listed. Commits directly to each
repo's default branch via the GitHub Contents API.

Usage:
    export GITHUB_TOKEN=ghp_...   # needs 'repo' scope (or an org-scoped
                                   # installation token) across target repos
    python rollout/add_workflow_to_repos.py --repos-file rollout/repos.txt
    python rollout/add_workflow_to_repos.py --repo owner/repo-a --repo owner/repo-b
"""
import argparse
import base64
import os
import sys

import requests

API = "https://api.github.com"
STUB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "consumer-workflow-stub.yml")
TARGET_PATH = ".github/workflows/pr-review.yml"


def get_default_branch(repo: str, headers: dict) -> str:
    resp = requests.get(f"{API}/repos/{repo}", headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["default_branch"]


def get_existing_sha(repo: str, headers: dict, branch: str) -> str | None:
    resp = requests.get(
        f"{API}/repos/{repo}/contents/{TARGET_PATH}",
        headers=headers, params={"ref": branch}, timeout=30,
    )
    return resp.json()["sha"] if resp.status_code == 200 else None


def push_workflow(repo: str, token: str) -> None:
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    try:
        with open(STUB_PATH, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode()

        branch = get_default_branch(repo, headers)
        existing_sha = get_existing_sha(repo, headers, branch)

        payload = {
            "message": "ci: add AI PR review workflow" if not existing_sha else "ci: update AI PR review workflow",
            "content": content_b64,
            "branch": branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha

        resp = requests.put(
            f"{API}/repos/{repo}/contents/{TARGET_PATH}", headers=headers, json=payload, timeout=30
        )
        if resp.status_code in (200, 201):
            print(f"  OK  {repo} ({'updated' if existing_sha else 'created'})")
        else:
            print(f"  FAIL {repo}: {resp.status_code} {resp.text[:200]}")
    except requests.RequestException as e:
        print(f"  FAIL {repo}: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", action="append", default=[], help="owner/name, repeatable")
    parser.add_argument("--repos-file", help="text file, one owner/name per line")
    args = parser.parse_args()

    repos = list(args.repo)
    if args.repos_file:
        with open(args.repos_file) as f:
            repos += [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not repos:
        print("No repos given. Use --repo owner/name (repeatable) or --repos-file.", file=sys.stderr)
        sys.exit(1)

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: set GITHUB_TOKEN.", file=sys.stderr)
        sys.exit(1)

    print(f"Rolling out to {len(repos)} repo(s)...")
    for repo in repos:
        push_workflow(repo, token)


if __name__ == "__main__":
    main()
