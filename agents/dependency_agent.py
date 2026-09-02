from agents.base_agent import Agent
from agents.prompt_loader import load_prompt
from tools.schemas import RUN_NPM_AUDIT, RUN_NPM_OUTDATED, FINISH_REVIEW
from tools.dependency_tools import run_npm_audit, run_npm_outdated

SYSTEM_PROMPT = load_prompt("dependency_system.md")

TOOLS = [RUN_NPM_AUDIT, RUN_NPM_OUTDATED, FINISH_REVIEW]
EXECUTOR = {
    "run_npm_audit": run_npm_audit,
    "run_npm_outdated": run_npm_outdated,
}


def run(diff_summary: str, context: dict) -> dict:
    agent = Agent(
        name="dependency-agent",
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_executor=EXECUTOR,
        max_turns=6,  # this one only needs 2 tool calls + finish, cap it tight
    )
    return agent.run(
        f"Review this pull request's dependency changes (package.json/"
        f"package-lock.json) for known vulnerabilities and outdated packages.\n\n{diff_summary}",
        context=context,
    )
