# pr-security-agent — Codebase Reference

Generated 2026-09-03 as a persistent reference for future sessions. Read this
first before making changes — it captures architecture, conventions, and
current in-progress work so a new session doesn't have to re-derive it.

## What this project is

A multi-agent, Claude-powered GitHub PR reviewer. A GitHub Actions workflow
(or a local script) fetches a PR's diff, runs an **orchestrator** agent that
decides which specialist agents are relevant, runs those specialists (each an
independent Claude tool-use loop with its own tools/prompt), aggregates their
findings, and posts one consolidated review to the PR via the GitHub REST
API (inline comments + summary + approve/comment/request_changes verdict).

Nothing here is a fixed pipeline — the orchestrator LLM decides which
specialists to dispatch based on the diff, and each specialist LLM decides
how many tool calls it needs before finishing. Language-agnostic by design:
the Python code only orchestrates (git diff, grep, semgrep, npm, Claude API
calls); it works on any language in the target repo.

## Directory map

```
agents/              Agent definitions (system prompt + tools + executor)
  base_agent.py       Generic Claude tool-use loop runner (the only place that calls anthropic.Anthropic())
  orchestrator.py      Decides which specialists to dispatch, aggregates findings
  security_agent.py    Vulnerabilities
  pr_review_agent.py   Correctness/logic bugs
  quality_agent.py     Maintainability
  dependency_agent.py  npm dependency audit (NEW, uncommitted)
  react_standards_agent.py  React coding standards: hooks rules, component structure, a11y (NEW, uncommitted)
  prompt_loader.py     Loads prompts/*.md relative to this package, cwd-independent
prompts/              System prompt = review rubric for each agent (*.md)
tools/
  analysis_tools.py    git diff, get_file_content, search_codebase (grep), run_semgrep — all operate on local working tree
  dependency_tools.py  run_npm_audit, run_npm_outdated (NEW, uncommitted)
  eslint_tools.py       run_eslint — bundled ESLint config, React/hooks/a11y rules (NEW, uncommitted)
  github_tools.py      GithubContext, get_pr, list_open_prs, post_review — the ONLY GitHub API calls
  schemas.py           Shared JSON tool schemas (input_schema for Claude tool-use) + FINDING_SCHEMA + FINISH_REVIEW variants
rules/                 Bundled Semgrep/ESLint rules, no network needed (NEW, uncommitted)
  security-rules.yml    SQLi (JS/TS/Python), dangerouslySetInnerHTML XSS, hardcoded secret patterns, open redirects
  eslint-react.eslintrc.json  eslint:recommended + react/react-hooks/jsx-a11y recommended configs (NEW, uncommitted)
.github/workflows/
  pr-review.yml          Standalone workflow: runs entirely from this repo's own code
  pr-review-reusable.yml Reusable workflow_call version: agent code lives in one central repo, callable from many
main.py                Actions entrypoint (reads env vars set by the workflow, calls orchestrator, posts review, exits 1 on request_changes)
review_pr.py            Local CLI: review a real PR by number, works outside Actions
watch_prs.py            Local poller: watches a repo for new/updated PRs, auto-reviews via review_pr.review_pr()
test_local.py           Local dry-run: diff any two git refs, print findings, nothing posted to GitHub
rollout/                Multi-repo rollout tooling (bulk-push the workflow stub to many repos via GitHub Contents API)
examples/setup_demo_repo.sh
```

## Execution flow

1. **Trigger**: GitHub Actions `pull_request` event (opened/synchronize/reopened), or manual `review_pr.py <PR#>`, or `watch_prs.py` polling, or `test_local.py` against two git refs (no posting).
2. **Diff**: `tools/analysis_tools.get_diff_summary(base_sha, head_sha)` — `git diff --name-status` + `git diff --unified=3`, truncated to 12,000 chars, capped at 60 files.
3. **Orchestrator** (`agents/orchestrator.py`): Claude decides which of 5 `dispatch_*_agent` tools to call (security / pr_review / quality / dependency / react_standards), based on `prompts/orchestrator_system.md` rules (e.g. dependency agent ONLY if diff touches package.json/package-lock.json; react_standards agent ONLY if diff touches .jsx/.tsx or React-flavored .js/.ts). Each dispatch tool call synchronously runs that specialist's full agent loop and returns its structured result as a tool_result.
4. **Specialists**: Each is its own `Agent` instance (`base_agent.Agent`) — independent message loop, own system prompt, own tools (`get_file_content`, `search_codebase`, plus `run_semgrep` for security, `run_npm_audit`/`run_npm_outdated` for dependency, or `run_eslint` for react_standards). Terminates by calling `finish_review` (required tool) with `{findings: [...], summary: "..."}`.
5. **Aggregation**: Orchestrator de-dupes overlapping findings (same file+line), decides overall verdict (`request_changes` if any critical/high, `comment` if only medium/low/info, `approve` if none), calls its own `finish_review` (which also carries `verdict`).
6. **Posting**: `tools/github_tools.post_review()` — one `POST /repos/{repo}/pulls/{pr}/reviews` call with inline `comments` (path/line/body) + summary body + review event (APPROVE/REQUEST_CHANGES/COMMENT).
7. **Exit code**: `main.py` exits 1 if verdict is `request_changes` — lets this be wired as a required status check to block merges.

## The `Agent` abstraction (`agents/base_agent.py`)

Generic driver, reused by every agent (orchestrator + all specialists):
- Constructor: `name, system_prompt, tools, tool_executor, model=AGENT_MODEL env (default claude-opus-5), max_turns=AGENT_MAX_TURNS env (default 15)`.
- `run(user_message, context)`: loops `messages.create()` → if `stop_reason != "tool_use"`, treats as done with empty findings (defensive, shouldn't normally trigger). Otherwise executes each tool_use block via `tool_executor[name](input, context)`, catches exceptions and feeds `{"error": str(e)}` back to the model rather than crashing. Loop ends when the model calls `finish_review` (its `input` becomes the final result) or turns run out.
- Every agent's tool list MUST include a `finish_review`-named tool — this is the hard-coded termination signal, checked by name (`block.name == "finish_review"`) not by any special typing.
- `tool_executor` is a plain `dict[str, callable(input_dict, context) -> dict|str]`. `context` is passed through unused by most current tools but exists for e.g. `base_sha`/`head_sha`.

## Tool inventory

| Tool | File | Used by | Notes |
|---|---|---|---|
| `get_file_content` | analysis_tools.py | security, pr_review, quality | Reads local file, line-numbered, capped at 800 lines |
| `search_codebase` | analysis_tools.py | security, pr_review, quality | Shells out to `grep -rn --exclude-dir=.git --exclude-dir=node_modules` |
| `run_semgrep` | analysis_tools.py | security only | Runs bundled `rules/security-rules.yml` (no network) AND `--config=auto` (registry, needs network, silently skipped if unreachable) |
| `run_npm_audit` | dependency_tools.py | dependency (new) | Wraps `npm audit --json` |
| `run_npm_outdated` | dependency_tools.py | dependency (new) | Wraps `npm outdated --json` |
| `run_eslint` | eslint_tools.py | react_standards (new) | Runs `npx eslint --no-eslintrc --config rules/eslint-react.eslintrc.json` on one file (eslint:recommended + react/react-hooks/jsx-a11y recommended); needs `eslint`+plugins installed by the workflow's "Install ESLint" step, degrades to empty findings if missing |
| `finish_review` | schemas.py | all specialists | Terminates the loop; `FINISH_REVIEW_WITH_VERDICT` variant used only by orchestrator (adds `verdict` enum) |

All file/grep/semgrep/npm tools run against the **local checked-out working
tree** — zero GitHub API calls except `github_tools.py`, which is only
invoked once at the very end to post the review (keeps things fast, avoids
GitHub API rate limits).

## Finding schema

```
{ file: str, line: int, severity: critical|high|medium|low|info,
  title: str, description: str, suggested_fix?: str }
```
`suggested_fix` (if present) renders as a GitHub `\`\`\`suggestion` block, directly
committable from the PR UI. Each posted comment is tagged `flagged by: <agent-name>`.

## Severity → verdict mapping (orchestrator prompt)

- Any `critical`/`high` finding → `request_changes`
- Only `medium`/`low`/`info` → `comment`
- No findings → `approve`

## Current uncommitted work (as of this snapshot, 2026-09-03)

Working tree has **two** specialist agents in progress, not yet committed:

**1. Dependency-audit agent** (`dependency_agent`):
- New: `agents/dependency_agent.py`, `prompts/dependency_system.md`, `tools/dependency_tools.py`, `rules/security-rules.yml`
- Modified: `agents/orchestrator.py` (dispatch tool + executor), `prompts/orchestrator_system.md` (dispatch rule: only when diff touches package.json/package-lock.json), `tools/analysis_tools.py` (bundled-rules Semgrep pass), `tools/schemas.py` (`RUN_NPM_AUDIT`/`RUN_NPM_OUTDATED`), both workflow YAMLs (Node.js setup + `npm ci --ignore-scripts`, conditional on package.json).

**2. React coding-standards agent** (`react_standards_agent`) — added in this session:
- New: `agents/react_standards_agent.py`, `prompts/react_standards_system.md`, `tools/eslint_tools.py`, `rules/eslint-react.eslintrc.json` (bundled config: `eslint:recommended` + `react`/`react-hooks`/`jsx-a11y` recommended rule sets, `react/prop-types` and `react/react-in-jsx-scope` turned off, `.ts`/`.tsx` override using `@typescript-eslint/parser`)
- Modified: `agents/orchestrator.py` (`dispatch_react_standards_agent` tool + executor, imports `react_standards_agent`), `prompts/orchestrator_system.md` (added specialist description + dispatch rule #6: only when diff touches `.jsx`/`.tsx` or React-flavored `.js`/`.ts`; renumbered the whole instruction list 1-10, fixing a pre-existing duplicate-"5." bug), `tools/schemas.py` (`RUN_ESLINT` schema), both workflow YAMLs (new "Install ESLint (for React coding standards agent)" step — `npm install --no-save --ignore-scripts eslint@^8 eslint-plugin-react eslint-plugin-react-hooks eslint-plugin-jsx-a11y @typescript-eslint/parser @typescript-eslint/eslint-plugin`, gated on `package.json` existing, `continue-on-error: true`), `README.md` (agent list + an "Note on ESLint" parity section next to the existing Semgrep note).
- Design choice: dedicated agent (not folded into `quality_agent`) so React rules can be tuned independently, mirroring how `dependency_agent` was added — user explicitly chose this over extending `quality_agent`.

Both are coherent, complete features — all pieces wired together and appear
finished, just not yet committed. Git history shows 4 commits total, most
recent being a workflow repo-reference fix (`02bf62b`).

## Two-workflow deployment model

- **`pr-review.yml`** — standalone: agent code (`agents/`, `tools/`, `prompts/`) lives directly in the target repo. Simple, but means copying the whole codebase into every repo you want reviewed.
- **`pr-review-reusable.yml`** — `workflow_call` version: agent code stays in ONE central repo (currently hardcoded as `AkashDoke/pr-security-agent` in the "Checkout agent code" step and in `rollout/consumer-workflow-stub.yml`); target repos get a ~10-line stub (`rollout/consumer-workflow-stub.yml`) that references it via `uses: .../pr-review-reusable.yml@main` + `secrets: inherit`. This is the intended scale-out path — see `rollout/README.md` for the full multi-repo rollout process (bulk script `rollout/add_workflow_to_repos.py` pushes the stub to many repos via the Contents API; org-level `ANTHROPIC_API_KEY` secret set once).
- Both workflows now conditionally set up Node.js and run `npm ci --ignore-scripts` (or `npm install --package-lock-only --ignore-scripts`) only `if: hashFiles('package.json') != ''`, feeding the new dependency agent. `--ignore-scripts` is deliberate defense-in-depth since this runs against attacker-controllable PR diffs.
- Documented future upgrade path (not yet built): swap `GITHUB_TOKEN` for a GitHub App (installed org-wide, short-lived installation tokens) and move `main.py` off Actions onto an Azure Function/Container App triggered by the App's webhook — `agents/`, `tools/analysis_tools.py`, `prompts/` wouldn't need to change.

## Local dev / testing entrypoints

- `test_local.py [--base REF] [--head REF] [--json]` — diffs two local git refs, runs the full orchestrator, prints findings. **Never posts to GitHub.** Fastest way to iterate on prompts/tools.
- `review_pr.py <PR#> [--repo owner/name] [--dry-run]` — reviews a real PR against the actual GitHub API from a local clone; posts unless `--dry-run`.
- `watch_prs.py --repo owner/name [--interval N]` — polls open PRs, auto-reviews new/updated ones, tracks state in `.pr_agent_state.json` to avoid re-review.
- All three ultimately call `agents.orchestrator.run(diff_summary, context)`.

## Config knobs

- `AGENT_MODEL` env var — default `claude-opus-5` (base_agent.py). Note: this is an older/placeholder model id in the code; current recommended models are the Claude 5 family (Sonnet 5, Opus 5) per environment note — worth checking if this should be updated.
- `AGENT_MAX_TURNS` env var — default 15 (10 for orchestrator explicitly, 6 for dependency agent explicitly — both override the env default in their `Agent(...)` construction).
- `ANTHROPIC_API_KEY`, `GITHUB_TOKEN` — required env vars everywhere.

## Fixed bug: 422 from GitHub on findings outside the diff (2026-09-03)

**Symptom**: `post_review()` → `resp.raise_for_status()` raised
`requests.exceptions.HTTPError: 422 Client Error: Unprocessable Entity` on
`POST /repos/.../pulls/.../reviews`, losing the entire review (no comments,
no summary posted) even though the orchestrator had produced valid findings.

**Root cause**: GitHub's create-review endpoint rejects the *whole batched
request* if even one inline comment's `line` isn't part of the PR's diff
hunks. Observed directly: `react_standards_agent` used `get_file_content` to
read full file context, noticed two genuinely pre-existing a11y issues in
`Navbar.jsx` (self-labeled `"Pre-existing... out of scope for this diff"` in
the finding title) and reported them anyway — those lines weren't in any
diff hunk, so the single POST 422'd and every other finding from every other
agent was silently dropped too.

**Fix** (both parts landed):
1. **Root cause** — added an explicit instruction to `security_system.md`,
   `pr_review_system.md`, `quality_system.md`, `react_standards_system.md`:
   only report findings on lines the diff actually changed; if
   `get_file_content` surfaces something pre-existing/out of scope, don't
   report it as a finding.
2. **Defense in depth** — `tools/analysis_tools.get_diff_line_map(base_sha,
   head_sha)` (new) parses the full (untruncated) unified diff and returns
   `{file: set(valid new-file line numbers)}` — every context/added line in
   every hunk, mirroring exactly what GitHub's API will accept for a `RIGHT`-side
   inline comment. `tools/github_tools.post_review()` now takes an optional
   `valid_lines` param: findings whose `(file, line)` isn't in that map are
   demoted into the summary body as a plain bulleted list instead of being
   sent as inline comments — so an errant out-of-diff finding (from any
   agent, including future ones) can no longer take the whole review down.
   `post_review()` also now prints the response body on a non-2xx status
   before re-raising, so any future failure is diagnosable directly from the
   Action log instead of a bare `HTTPError` with no detail.
   `main.py` and `review_pr.py` both now call `get_diff_line_map()` and pass
   it through. Verified the line-map parser against a crafted diff (50-line
   file, one line changed) — correctly returns only the `unified=3` hunk
   window (±3 lines), not the whole file.
3. `dependency_agent` findings run through the same `valid_lines` filter
   automatically (no prompt change needed there) since it's applied
   generically at the `post_review()` layer, not per-agent.

## Known constraints / gotchas worth remembering

- `run_semgrep`'s registry pass (`--config=auto`) needs network access to semgrep.dev; fails silently (empty findings) on restricted-egress self-hosted runners — the bundled `rules/security-rules.yml` pass is the guaranteed-network-free fallback, which is presumably *why* `rules/` was just added.
- `get_diff_summary` truncates diffs over 12,000 chars and caps at 60 changed files — very large PRs will get a partial diff.
- `get_file_content` caps at 800 lines per file.
- `Agent.run` catches tool executor exceptions per-call (doesn't crash the whole review) but does NOT retry Claude API errors themselves.
- Dependency agent hardcodes npm/package.json — no support for pip/poetry/cargo/etc yet.
- `run_eslint`'s bundled ruleset needs `eslint` + 5 plugin packages installed at job setup time (npm install, not bundled/vendored) — heavier network dependency than Semgrep's bundled pass (which needs no npm packages, just the `semgrep` binary + a local `.yml`). If that install step is skipped/fails, `run_eslint` silently returns empty findings (same graceful-degradation philosophy as the other tools) rather than failing the review.
- `run_eslint` is pinned to ESLint 8.x (legacy `.eslintrc` config format via `--no-eslintrc --config`) rather than ESLint 9's flat config, for broadest compatibility with existing React repos still on v8.
- The reusable workflow's central-repo reference (`AkashDoke/pr-security-agent`) is hardcoded in two places (`pr-review-reusable.yml` and `rollout/consumer-workflow-stub.yml`) — must stay in sync if the repo is renamed/moved (this was literally the subject of the most recent commit, `02bf62b`).

## Adding a new specialist agent (documented pattern, per README)

1. Copy `agents/security_agent.py` (or `dependency_agent.py`) as a template.
2. Write its rubric in `prompts/<name>_system.md`.
3. Add tool schemas to `tools/schemas.py` if it needs new tools; implement them in `tools/`.
4. Add a `dispatch_<name>_agent` tool + executor entry in `agents/orchestrator.py`.
5. Update `prompts/orchestrator_system.md` with dispatch criteria for when to run it.
