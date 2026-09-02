"""
Generic Claude agent runner: manages the tool-use loop for any agent.
An agent is defined by: a system prompt, a list of tool schemas, and a
tool_executor dict mapping tool name -> callable(input_dict, context) -> result.

Every agent MUST expose a `finish_review` tool as its termination signal.
When the model calls it, the loop stops and returns that tool's input as
the agent's final structured result.
"""
import json
import os
import anthropic

DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "claude-opus-5")
DEFAULT_MAX_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "15"))


class Agent:
    def __init__(self, name, system_prompt, tools, tool_executor,
                 model=DEFAULT_MODEL, max_turns=DEFAULT_MAX_TURNS):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.tool_executor = tool_executor
        self.model = model
        self.max_turns = max_turns
        self.client = anthropic.Anthropic()

    def run(self, user_message: str, context: dict | None = None) -> dict:
        context = context or {}
        messages = [{"role": "user", "content": user_message}]
        turns = 0
        final_result = None

        while turns < self.max_turns:
            turns += 1
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                tools=self.tools,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                # Model stopped without calling finish_review — treat as done,
                # no structured findings (shouldn't normally happen if the
                # prompt is well-written, but don't hang forever).
                final_result = {
                    "findings": [],
                    "summary": self._extract_text(response) or f"{self.name} ended without finish_review.",
                    "verdict": "comment",
                }
                break

            tool_results = []
            finished = False
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                if block.name == "finish_review":
                    final_result = block.input
                    finished = True
                    continue
                try:
                    result = self.tool_executor[block.name](block.input, context)
                except Exception as e:  # noqa: BLE001 — surface tool errors back to the model
                    result = {"error": str(e)}
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result if isinstance(result, str) else json.dumps(result),
                })

            if finished:
                break
            if tool_results:
                messages.append({"role": "user", "content": tool_results})
            else:
                break

        if final_result is None:
            final_result = {
                "findings": [],
                "summary": f"{self.name} hit max_turns ({self.max_turns}) without finishing.",
                "verdict": "comment",
            }
        final_result.setdefault("agent", self.name)
        return final_result

    @staticmethod
    def _extract_text(response) -> str:
        return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
