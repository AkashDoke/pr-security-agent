"""
Tools for checking npm dependency health: known vulnerabilities (npm audit)
and outdated packages with upgrade targets (npm outdated). Both operate on
the checked-out working tree, same as the other tools in this package.
"""
import json
import re
import subprocess

MAX_TIMEOUT = 120


def _run_json(cmd: list[str], cwd: str = ".") -> dict:
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=MAX_TIMEOUT)
        # npm audit/outdated exit non-zero when they find something — that's
        # normal, not a failure. Only a genuinely empty/unparseable stdout
        # means the command itself didn't work.
        return json.loads(out.stdout) if out.stdout.strip() else {}
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}


def _find_line_in_package_json(package_name: str, package_json_path: str = "package.json") -> int:
    """Best-effort: find which line a dependency is declared on, for
    posting an inline comment at a sensible spot."""
    try:
        with open(package_json_path) as f:
            for i, line in enumerate(f, start=1):
                if re.search(rf'"{re.escape(package_name)}"\s*:', line):
                    return i
    except FileNotFoundError:
        pass
    return 1


def run_npm_audit(input_dict: dict, context: dict) -> dict:
    """Known vulnerabilities in current dependencies, via the npm/GitHub
    advisory database."""
    data = _run_json(["npm", "audit", "--json"])
    vulnerabilities = data.get("vulnerabilities", {})

    findings = []
    for pkg_name, info in vulnerabilities.items():
        advisories = [v for v in info.get("via", []) if isinstance(v, dict)]
        titles = [a.get("title", "") for a in advisories if a.get("title")]
        urls = [a.get("url", "") for a in advisories if a.get("url")]
        findings.append({
            "package": pkg_name,
            "severity": info.get("severity", "unknown"),
            "is_direct": info.get("isDirect", False),
            "advisories": titles[:3],  # cap so context doesn't balloon on packages with many CVEs
            "reference_urls": urls[:3],
            "line": _find_line_in_package_json(pkg_name),
        })
    return {"vulnerability_count": len(findings), "vulnerabilities": findings}


def run_npm_outdated(input_dict: dict, context: dict) -> dict:
    """Packages with a newer version available, current vs. latest."""
    data = _run_json(["npm", "outdated", "--json"])

    outdated = []
    for pkg_name, info in data.items():
        current = info.get("current") or info.get("wanted", "unknown")
        latest = info.get("latest", "unknown")
        outdated.append({
            "package": pkg_name,
            "current": current,
            "latest": latest,
            "line": _find_line_in_package_json(pkg_name),
        })
    return {"outdated_count": len(outdated), "outdated": outdated}
