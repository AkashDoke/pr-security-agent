from agents.base_agent import Agent
from agents import security_agent, pr_review_agent, quality_agent, dependency_agent, react_standards_agent
from tools.schemas import FINISH_REVIEW_WITH_VERDICT
from agents.prompt_loader import load_prompt

SYSTEM_PROMPT = load_prompt("orchestrator_system.md")

DISPATCH_TOOLS = [
    {
        "name": "dispatch_security_agent",
        "description": "Run the security specialist agent on this PR. Use for any code touching auth, input handling, DB queries, crypto, file I/O, secrets, or external calls.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "dispatch_pr_review_agent",
        "description": "Run the general PR review agent on this PR (correctness, bugs, edge cases). Use for most non-trivial code changes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "dispatch_quality_agent",
        "description": "Run the code quality/maintainability agent on this PR. Use for larger changes, refactors, or new modules; skip for tiny fixes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "dispatch_dependency_agent",
        "description": "Run the dependency audit agent. Use ONLY when the diff touches package.json or package-lock.json -- checks for known-vulnerable packages and outdated versions with upgrade suggestions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "dispatch_react_standards_agent",
        "description": "Run the React coding standards agent. Use when the diff touches .jsx/.tsx files or .js/.ts files containing React components/hooks -- checks Rules of Hooks, component structure, key props, accessibility, and consistency with existing React patterns. Skip for non-React diffs.",
        "input_schema": {"type": "object", "properties": {}},
    },
]
TOOLS = DISPATCH_TOOLS + [FINISH_REVIEW_WITH_VERDICT]


def _make_dispatch_executor(diff_summary: str):
    def dispatch_security_agent(_input, context):
        return security_agent.run(diff_summary, context)

    def dispatch_pr_review_agent(_input, context):
        return pr_review_agent.run(diff_summary, context)

    def dispatch_quality_agent(_input, context):
        return quality_agent.run(diff_summary, context)

    def dispatch_dependency_agent(_input, context):
        return dependency_agent.run(diff_summary, context)

    def dispatch_react_standards_agent(_input, context):
        return react_standards_agent.run(diff_summary, context)

    return {
        "dispatch_security_agent": dispatch_security_agent,
        "dispatch_pr_review_agent": dispatch_pr_review_agent,
        "dispatch_quality_agent": dispatch_quality_agent,
        "dispatch_dependency_agent": dispatch_dependency_agent,
        "dispatch_react_standards_agent": dispatch_react_standards_agent,
    }


def run(diff_summary: str, context: dict | None = None) -> dict:
    """Runs the orchestrator, which decides which specialist agents to call,
    then aggregates their findings into one final verdict + finding list."""
    agent = Agent(
        name="orchestrator",
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_executor=_make_dispatch_executor(diff_summary),
        max_turns=10,
    )
    return agent.run(
        f"A pull request needs review. Decide which specialist agents to run, "
        f"then aggregate their findings into a final review.\n\n{diff_summary}",
        context=context or {},
    )
