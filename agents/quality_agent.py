from agents.base_agent import Agent
from tools.schemas import GET_FILE_CONTENT, SEARCH_CODEBASE, FINISH_REVIEW
from tools.analysis_tools import get_file_content, search_codebase
from agents.prompt_loader import load_prompt

SYSTEM_PROMPT = load_prompt("quality_system.md")

TOOLS = [GET_FILE_CONTENT, SEARCH_CODEBASE, FINISH_REVIEW]
EXECUTOR = {
    "get_file_content": get_file_content,
    "search_codebase": search_codebase,
}


def run(diff_summary: str, context: dict) -> dict:
    agent = Agent(
        name="quality-agent",
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_executor=EXECUTOR,
    )
    return agent.run(
        f"Review this pull request diff for code quality and maintainability issues.\n\n{diff_summary}",
        context=context,
    )
