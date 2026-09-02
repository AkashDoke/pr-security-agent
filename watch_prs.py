#!/usr/bin/env python3
"""
Polls a repo for open PRs and automatically reviews any that are new or have
new commits since the last check — runs entirely on your machine, no
webhook/server/public URL needed. Leave it running in a terminal; Ctrl+C to
stop.

Tracks what it's already reviewed in .pr_agent_state.json (in the current
directory) so restarts don't re-review unchanged PRs.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    export GITHUB_TOKEN=ghp_...
    cd /path/to/your/local/clone
    python watch_prs.py --repo owner/name              # polls every 60s
    python watch_prs.py --repo owner/name --interval 20
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.github_tools import list_open_prs
from review_pr import get_token, review_pr

STATE_FILE = ".pr_agent_state.json"


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--interval", type=int, default=60, help="poll interval in seconds (default: 60)")
    args = parser.parse_args()

    token = get_token()
    state = load_state()

    print(f"Watching {args.repo} for PR activity every {args.interval}s. Ctrl+C to stop.")
    while True:
        try:
            prs = list_open_prs(args.repo, token)
            for pr in prs:
                number, head_sha = pr["number"], pr["head"]["sha"]
                if state.get(str(number)) == head_sha:
                    continue  # already reviewed this exact commit, skip

                print(f"\n[{time.strftime('%H:%M:%S')}] New/updated PR #{number} detected "
                      f"(head={head_sha[:7]}) — reviewing...")
                try:
                    review_pr(args.repo, number, token, dry_run=False)
                    state[str(number)] = head_sha
                    save_state(state)
                except Exception as e:  # noqa: BLE001 — keep the watcher alive across errors
                    print(f"  error reviewing PR #{number}: {e}")
        except Exception as e:  # noqa: BLE001 — e.g. transient network/API errors
            print(f"poll error: {e}")

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
