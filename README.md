# PR Security & Review Agent (Claude, multi-agent)

Multi-agent PR reviewer: an **Orchestrator** agent decides which specialist
agents to run on a given PR, each specialist works autonomously with its own
tools, and the orchestrator aggregates their findings into one posted GitHub
review.

Agents:
- `orchestrator` — decides which specialists to dispatch, aggregates results
- `security_agent` — vulnerabilities (injection, auth, secrets, crypto, etc.)
- `pr_review_agent` — correctness, logic bugs, edge cases
- `quality_agent` — maintainability, structure, duplication

Each specialist has its own tools (`get_file_content`, `search_codebase`,
and `run_semgrep` for security) and decides on its own how many tool calls
it needs before calling `finish_review`. Nothing here is a fixed pipeline —
the model controls the flow.

---

## Setup

### 1. Get an Anthropic API key
Create one at console.anthropic.com if you don't have one.

### 2. Add it as a repo secret
In the **target repo** (the one you want reviewed — this can be this repo
itself or any other):
`Settings → Secrets and variables → Actions → New repository secret`
- Name: `ANTHROPIC_API_KEY`
- Value: your key

`GITHUB_TOKEN` is provided automatically by Actions — no setup needed, as
long as the workflow has `pull-requests: write` permission (already set in
the workflow file below).

### 3. Copy these files into the target repo
Copy the entire contents of this project into the root of the repo you want
reviewed:
```
.github/workflows/pr-review.yml
agents/
tools/
prompts/
main.py
requirements.txt
```

### 4. Commit and push to the default branch
The workflow only takes effect once it exists on the default branch (GitHub
requires this for `pull_request`-triggered workflows).

### 5. Open a test PR
Push a branch with a deliberately flawed change (e.g. a hardcoded secret or
a string-concatenated SQL query) and open a PR. Within roughly 30-90 seconds
you should see:
- Inline review comments on the flagged lines
- A summary comment at the top
- A review state of "Changes requested" (if severity is critical/high) or
  "Commented" otherwise

### 6. Run it locally instead of via Actions (optional)
Two ways to run this on your own machine against **real** PRs — nothing
gets set up on GitHub Actions for this path, and reviews still post to the
actual PR on GitHub.

**On demand** — review a specific PR right now:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GITHUB_TOKEN=ghp_...     # needs pull-requests write scope; or run `gh auth login` and skip this
cd /path/to/your/local/clone
python review_pr.py 42                     # review PR #42; repo auto-detected from `origin`
python review_pr.py 42 --dry-run           # preview findings, don't post anything
```

**Automatic** — leave a watcher running that reviews any new PR (or new
commits pushed to an existing PR) as soon as it appears, checked every N
seconds:
```bash
python watch_prs.py --repo owner/name --interval 30
```
Leave that running in a terminal (or `tmux`/`screen`) while you work — open
a PR from your usual workflow, and within one poll interval it gets
reviewed and commented on for real. It tracks what it's already reviewed in
`.pr_agent_state.json` so restarting the watcher won't re-review unchanged
PRs. There's no webhook or public URL involved — it's just polling the
GitHub API, so it only works while the watcher process is actually running
on your machine.

Both scripts fetch the PR's real base/head SHAs from the GitHub API, then
`git fetch` those commits into your local clone so the diff/file-reading
tools can operate on them exactly as they do in Actions.

### Language support
Nothing here is Python-specific — the agent code (`agents/`, `tools/`) is
Python, but it only orchestrates: reading diffs, grepping, running Semgrep,
and calling Claude. All of that operates on whatever language is in the
repo. Verified working against a React/TypeScript (`.tsx`) diff including
JSX syntax during development of this project — diffing, `get_file_content`,
`search_codebase`, and Semgrep's TSX parsing all handle it correctly.

The `security_system.md` prompt includes frontend-specific vulnerability
classes (XSS via `dangerouslySetInnerHTML`/`innerHTML`, hardcoded secrets in
client bundles, open redirects, insecure `postMessage`, client-side-only
auth checks, sensitive data in `localStorage`) alongside the general/backend
ones — tune it further for your stack (Vue, Angular, etc.) if needed.

**Note on Semgrep:** `run_semgrep` uses `--config=auto`, which downloads
rules from Semgrep's registry over the network at run time. This works by
default on GitHub-hosted Actions runners (they have full internet access).
If you're on a self-hosted runner with restricted egress, `--config=auto`
will fail — pin to a specific ruleset instead (e.g.
`--config=p/javascript --config=p/typescript --config=p/react --config=p/secrets`
in `tools/analysis_tools.py`), which still needs registry access once to
fetch those, or vendor rules locally as `.yml` files and point
`--config=/path/to/rules` at them for a fully offline setup.

### 7. (Optional) Make it a required check

`Settings → Branches → Branch protection rules → Require status checks to
pass` → add `review (AI PR Review)`. This blocks merges when the agent
returns `request_changes` — since `main.py` exits non-zero in that case, the
Action job itself shows as failed.

---

## Customizing

- **Review standards**: edit `prompts/security_system.md`,
  `prompts/pr_review_system.md`, `prompts/quality_system.md` — these are the
  actual review rubric each agent follows. Add your org's specific standards,
  known-bad patterns, or exemptions here.
- **Which agents get dispatched**: edit `prompts/orchestrator_system.md` to
  change the dispatch logic (e.g. always run quality_agent regardless of
  size, or add a new specialist).
- **Add a new specialist agent**: copy `agents/security_agent.py` as a
  template, write its prompt in `prompts/`, add a `dispatch_<name>_agent`
  tool + executor entry in `agents/orchestrator.py`.
- **Model/turn budget**: set `AGENT_MODEL` and `AGENT_MAX_TURNS` env vars in
  the workflow file to override the defaults in `agents/base_agent.py`.
- **Cost control**: the orchestrator is instructed to skip agents that
  aren't relevant to a given diff — tune that logic in its prompt if you
  find it's over- or under-dispatching.

---

## Architecture notes

- All file reading, grepping, and Semgrep runs happen against the **local
  checked-out working tree** (`actions/checkout` puts the PR head commit on
  disk) — no GitHub API calls needed for those, which keeps things fast and
  avoids rate limits.
- The GitHub API is only called once, at the very end, to post the
  consolidated review (`tools/github_tools.py`).
- Each specialist agent is a fully independent `Agent` instance (see
  `agents/base_agent.py`) — the orchestrator invokes them synchronously as
  tool calls and gets their structured findings back as tool results.

## Upgrade path (multi-repo / org-wide)

This POC uses the Actions-provided `GITHUB_TOKEN`, scoped to one repo and
one workflow run. For org-wide deployment across many repos, swap
`tools/github_tools.py`'s auth for a **GitHub App** (installed once per
org, short-lived installation tokens minted per job) and move `main.py`
off Actions into an Azure Function/Container App triggered by the App's
webhook — the agent code itself (`agents/`, `tools/analysis_tools.py`,
`prompts/`) doesn't need to change.
