"""
Runs ESLint against a single React/JS/TS file using a bundled, repo-independent
ruleset (rules/eslint-react.eslintrc.json: eslint:recommended + react,
react-hooks, and jsx-a11y recommended configs), so results don't depend on
whatever ESLint config (if any) exists in the target repo.

Requires eslint + the plugins referenced by that config to be installed in
the job (see the "Install ESLint" step in .github/workflows/*.yml) -- that's
an npm/network dependency at setup time, not at rule-evaluation time, same
tradeoff as Semgrep's registry pass in analysis_tools.py.
"""
import json
import os
import subprocess

RULES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules")
ESLINT_CONFIG = os.path.join(RULES_DIR, "eslint-react.eslintrc.json")


def _run(cmd: list[str], cwd: str = ".") -> str:
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
        return out.stdout or ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def run_eslint(input_dict: dict, context: dict) -> dict:
    path = input_dict["path"]
    raw = _run([
        "npx", "--no-install", "eslint",
        "--no-eslintrc", "--config", ESLINT_CONFIG,
        "--format", "json", path,
    ])
    return {"path": path, "findings": _parse_eslint_json(raw, path)}


def _parse_eslint_json(raw_output: str, path: str) -> list[dict]:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        return []  # eslint/plugins not installed, or a config/parse error -- skip, don't crash the tool
    findings = []
    for file_result in parsed:
        for msg in file_result.get("messages", []):
            findings.append({
                "path": file_result.get("filePath", path),
                "line": msg.get("line"),
                "rule_id": msg.get("ruleId"),
                "message": msg.get("message"),
                "severity": "error" if msg.get("severity") == 2 else "warning",
            })
    return findings
