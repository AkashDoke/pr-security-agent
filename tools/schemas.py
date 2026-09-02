"""Reusable JSON tool schemas shared by specialist agents."""

GET_FILE_CONTENT = {
    "name": "get_file_content",
    "description": "Fetch the full content of a file in the repo at the PR head commit, with line numbers. Use when the diff alone doesn't give enough context to judge a finding.",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Repo-relative file path"}},
        "required": ["path"],
    },
}

SEARCH_CODEBASE = {
    "name": "search_codebase",
    "description": "Grep the repository for a text pattern to find related usages, callers, or definitions.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}

RUN_SEMGREP = {
    "name": "run_semgrep",
    "description": "Run Semgrep static security analysis on a specific file and return its findings. Runs both a bundled deterministic ruleset (SQL injection, XSS, hardcoded secrets, open redirects — no network needed) and Semgrep's broader registry ruleset (best-effort, needs network).",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
}

RUN_ESLINT = {
    "name": "run_eslint",
    "description": "Run ESLint against a specific React/JS/TS file using a bundled ruleset (eslint:recommended + react, react-hooks, and jsx-a11y recommended rules) and return its findings. Deterministic, does not depend on the target repo's own ESLint config.",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
}

RUN_NPM_AUDIT = {
    "name": "run_npm_audit",
    "description": "Check the repo's npm dependencies for known security vulnerabilities (via the npm/GitHub advisory database). Returns each vulnerable package, severity, and advisory titles/links.",
    "input_schema": {"type": "object", "properties": {}},
}

RUN_NPM_OUTDATED = {
    "name": "run_npm_outdated",
    "description": "Check the repo's npm dependencies for available updates. Returns each outdated package with its current and latest available version.",
    "input_schema": {"type": "object", "properties": {}},
}

FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "file": {"type": "string"},
        "line": {"type": "integer"},
        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "suggested_fix": {"type": "string", "description": "Optional code suggestion"},
    },
    "required": ["file", "line", "severity", "title", "description"],
}

FINISH_REVIEW = {
    "name": "finish_review",
    "description": "Call this exactly once, when you are done reviewing, to submit your findings.",
    "input_schema": {
        "type": "object",
        "properties": {
            "findings": {"type": "array", "items": FINDING_SCHEMA},
            "summary": {"type": "string", "description": "1-3 sentence summary of your review"},
        },
        "required": ["findings", "summary"],
    },
}

# Orchestrator's finish tool also carries an overall verdict
FINISH_REVIEW_WITH_VERDICT = {
    "name": "finish_review",
    "description": "Call this exactly once, when you are done aggregating all specialist agent findings.",
    "input_schema": {
        "type": "object",
        "properties": {
            "findings": {"type": "array", "items": FINDING_SCHEMA},
            "verdict": {"type": "string", "enum": ["approve", "request_changes", "comment"]},
            "summary": {"type": "string"},
        },
        "required": ["findings", "verdict", "summary"],
    },
}
