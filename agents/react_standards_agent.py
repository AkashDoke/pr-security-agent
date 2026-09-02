from agents.base_agent import Agent
from tools.schemas import GET_FILE_CONTENT, SEARCH_CODEBASE, RUN_ESLINT, FINISH_REVIEW
from tools.analysis_tools import get_file_content, search_codebase
from tools.eslint_tools import run_eslint
from agents.prompt_loader import load_prompt

SYSTEM_PROMPT = load_prompt("react_standards_system.md")

TOOLS = [GET_FILE_CONTENT, SEARCH_CODEBASE, RUN_ESLINT, FINISH_REVIEW]
EXECUTOR = {
    "get_file_content": get_file_content,
    "search_codebase": search_codebase,
    "run_eslint": run_eslint,
}


def run(diff_summary: str, context: dict) -> dict:
    agent = Agent(
        name="react-standards-agent",
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_executor=EXECUTOR,
    )
    return agent.run(
        f"Review this pull request diff for React coding standards and best-practice adherence.\n\n{diff_summary}",
        context=context,
    )
