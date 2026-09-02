"""
GitHub REST API calls. Only used for posting the final review — everything
else the agents need comes from the local checked-out working tree.
"""
import requests

API = "https://api.github.com"


class GithubContext:
    def __init__(self, token: str, repo: str, pr_number: int, head_sha: str):
        self.token = token
        self.repo = repo  # "owner/name"
        self.pr_number = pr_number
        self.head_sha = head_sha

    @property
    def headers(self):
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github+json",
        }


VERDICT_TO_EVENT = {
    "approve": "APPROVE",
    "request_changes": "REQUEST_CHANGES",
    "comment": "COMMENT",
}


def get_pr(repo: str, pr_number: int, token: str) -> dict:
    """Fetch PR metadata (base/head SHAs, title, branches) from the GitHub API."""
    resp = requests.get(
        f"{API}/repos/{repo}/pulls/{pr_number}",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def list_open_prs(repo: str, token: str) -> list[dict]:
    """List open PRs for a repo — used by the local watcher to detect new/updated PRs."""
    resp = requests.get(
        f"{API}/repos/{repo}/pulls",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
        params={"state": "open", "per_page": 100},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def post_review(ctx: GithubContext, findings: list[dict], verdict: str, summary: str) -> dict:
    comments = []
    for f in findings:
        body = f"**[{f.get('severity','info').upper()}] {f.get('title','Finding')}**\n\n{f.get('description','')}"
        if f.get("suggested_fix"):
            body += f"\n\n```suggestion\n{f['suggested_fix']}\n```"
        if f.get("agent"):
            body += f"\n\n<sub>flagged by: {f['agent']}</sub>"
        comments.append({"path": f["file"], "line": int(f["line"]), "body": body})

    payload = {
        "commit_id": ctx.head_sha,
        "event": VERDICT_TO_EVENT.get(verdict, "COMMENT"),
        "body": summary,
        "comments": comments,
    }
    resp = requests.post(
        f"{API}/repos/{ctx.repo}/pulls/{ctx.pr_number}/reviews",
        headers=ctx.headers, json=payload, timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
