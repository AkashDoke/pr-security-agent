# Assigning the agent to multiple repos

Don't copy the whole codebase into every repo. Use the **reusable workflow**
pattern: the agent code stays in this repo, target repos get a ~10-line
stub that calls it.

## One-time setup (do this once)

### 1. Make this repo callable as a reusable workflow
- Push this repo to GitHub as `your-org/pr-security-agent`.
- Edit `.github/workflows/pr-review-reusable.yml`: replace
  `your-org/pr-security-agent` with your actual org/repo in the "Checkout
  agent code" step.
- Edit `rollout/consumer-workflow-stub.yml` the same way.
- If this repo is **private**: `Settings → Actions → General → Access` in
  *this* repo → allow access from repos in your organization (otherwise
  other repos can't call its reusable workflow).

### 2. Set the API key ONCE, at the org level
`Organization settings → Secrets and variables → Actions → New organization
secret`
- Name: `ANTHROPIC_API_KEY`
- Repository access: all repos, or select the specific ones you're rolling
  this out to.

This is the actual point of doing it this way — you're not pasting the key
into 30 different repo secret pages.

## Rolling out to target repos

**A few repos — do it manually.** Copy `rollout/consumer-workflow-stub.yml`
into each target repo as `.github/workflows/pr-review.yml`, commit to its
default branch.

**Many repos — use the bulk script.**
```bash
export GITHUB_TOKEN=ghp_...   # needs repo write access to all target repos
python rollout/add_workflow_to_repos.py --repos-file rollout/repos.txt
```
Edit `rollout/repos.txt` first (one `owner/repo` per line), or pass repos
individually with repeated `--repo owner/name` flags. This commits the
stub workflow file directly to each repo's default branch via the GitHub
API — safe to re-run, it updates in place if the file already exists.

Each target repo needs `pull-requests: write` permission granted to
Actions (usually on by default; check `Settings → Actions → General →
Workflow permissions` if reviews aren't posting).

## Pinning versions

`consumer-workflow-stub.yml` calls `...pr-review-reusable.yml@main` by
default — fine for a pilot, risky at scale, since editing a prompt in
`main` instantly changes behavior on every repo using it simultaneously.
Once you're past the pilot:
1. Tag a release in the agent repo: `git tag v1.0.0 && git push --tags`
2. Change the stub (and re-run the rollout script) to point at
   `...pr-review-reusable.yml@v1.0.0` instead of `@main`.
3. Bump the tag deliberately when you want to roll out a change, rather
   than every repo picking it up the instant you push to `main`.

## Scaling further: when to move off Actions entirely

Reusable workflows work well up to tens of repos across one org. If you
get into the dozens-to-hundreds range, or need this across multiple
GitHub orgs, or want zero workflow files in target repos at all, that's
when it's worth switching to the **GitHub App + centralized service**
architecture instead (see the "Upgrade path" note in the main README):
install one GitHub App org-wide, target repos need no workflow file
whatsoever, and the service (Azure Function/Container App) reacts to the
App's webhook directly. The `agents/`, `tools/analysis_tools.py`, and
`prompts/` code doesn't change either way — only how it's triggered and
where it runs.
