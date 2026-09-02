"""
Tools that operate on the already-checked-out repo working tree
(actions/checkout has the PR head commit on disk). No GitHub API calls here.
"""
import json
import os
import re
import subprocess

MAX_OUTPUT_CHARS = 12000


def _run(cmd: list[str], cwd: str = ".") -> str:
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
        return (out.stdout or "") + (("\n" + out.stderr) if out.returncode != 0 else "")
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out"


def get_diff_summary(base_sha: str, head_sha: str, max_files: int = 60) -> str:
    """Compact unified diff for the whole PR, used as initial context for agents."""
    names = _run(["git", "diff", "--name-status", f"{base_sha}...{head_sha}"]).strip()
    files = [line.split("\t")[-1] for line in names.splitlines() if line.strip()][:max_files]
    diff = _run(["git", "diff", "--unified=3", f"{base_sha}...{head_sha}", "--", *files])
    if len(diff) > MAX_OUTPUT_CHARS:
        diff = diff[:MAX_OUTPUT_CHARS] + "\n...[diff truncated]..."
    return f"Changed files ({len(files)}):\n" + "\n".join(files) + "\n\nDiff:\n" + diff


def get_diff_line_map(base_sha: str, head_sha: str) -> dict[str, set[int]]:
    """Maps each changed file to the set of new-file line numbers that are
    actually part of the diff (added or context lines). GitHub's create-review
    API rejects the whole review with 422 if any inline comment's `line`
    isn't one of these -- used to filter findings before posting so one
    out-of-diff line doesn't take down every other finding with it.

    Not subject to get_diff_summary's char/file truncation -- correctness
    here matters more than prompt-context size, and this never reaches the LLM.
    """
    diff = _run(["git", "diff", "--unified=3", f"{base_sha}...{head_sha}"])
    valid: dict[str, set[int]] = {}
    current_file = None
    new_line_no = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            current_file = target[2:] if target.startswith("b/") else None
            new_line_no = None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            new_line_no = int(m.group(1)) if m else None
        elif current_file is None or new_line_no is None:
            continue
        elif line.startswith("+") and not line.startswith("+++"):
            valid.setdefault(current_file, set()).add(new_line_no)
            new_line_no += 1
        elif line.startswith(" "):
            valid.setdefault(current_file, set()).add(new_line_no)
            new_line_no += 1
        # lines starting with "-" (removed) don't exist in the new file and
        # don't advance new_line_no; other lines (e.g. "\ No newline...") ignored
    return valid


def get_file_content(input_dict: dict, context: dict) -> dict:
    path = input_dict["path"]
    try:
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()
        numbered = "".join(f"{i+1}: {line}" for i, line in enumerate(lines[:800]))
        return {"path": path, "content": numbered}
    except FileNotFoundError:
        return {"error": f"file not found: {path}"}


def search_codebase(input_dict: dict, context: dict) -> dict:
    query = input_dict["query"]
    out = _run(["grep", "-rn", "--exclude-dir=.git", "--exclude-dir=node_modules", query, "."])
    if len(out) > MAX_OUTPUT_CHARS:
        out = out[:MAX_OUTPUT_CHARS] + "\n...[results truncated]..."
    return {"query": query, "matches": out or "no matches"}


RULES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules")


def run_semgrep(input_dict: dict, context: dict) -> dict:
    path = input_dict["path"]
    findings = []

    # Bundled rules — no network dependency, guaranteed to run. Covers SQL
    # injection, XSS, hardcoded secrets, open redirects deterministically,
    # regardless of whether the registry below is reachable.
    bundled = _run(["semgrep", f"--config={RULES_DIR}/security-rules.yml", "--json", "--quiet", path])
    findings += _parse_semgrep_json(bundled, path, source="bundled")

    # Registry rules — broader coverage, but needs network access to
    # semgrep.dev. Works by default on GitHub-hosted Actions runners; skip
    # silently if unreachable (e.g. self-hosted runner with restricted
    # egress) rather than failing the whole review.
    auto = _run(["semgrep", "--config=auto", "--json", "--quiet", path])
    findings += _parse_semgrep_json(auto, path, source="registry")

    return {"path": path, "findings": findings}


def _parse_semgrep_json(raw_output: str, path: str, source: str) -> list[dict]:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        return []  # registry unreachable or other non-JSON error — skip, don't crash the tool
    return [
        {
            "path": r.get("path", path),
            "line": r.get("start", {}).get("line"),
            "rule_id": r.get("check_id"),
            "message": r.get("extra", {}).get("message"),
            "severity": r.get("extra", {}).get("severity"),
            "source": source,
        }
        for r in parsed.get("results", [])
    ]
