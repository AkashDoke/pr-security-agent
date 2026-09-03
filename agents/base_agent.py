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

DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5")
DEFAULT_MAX_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "15"))
# 4096 is too tight once findings carry suggested_fix code blocks -- the
# orchestrator especially can blow past it aggregating several specialists'
# findings into one finish_review call, truncating mid-tool-call (see the
# stop_reason handling in run() below).
DEFAULT_MAX_TOKENS = int(os.environ.get("AGENT_MAX_TOKENS", "8192"))


class Agent:
    def __init__(self, name, system_prompt, tools, tool_executor,
                 model=DEFAULT_MODEL, max_turns=DEFAULT_MAX_TURNS, max_tokens=DEFAULT_MAX_TOKENS):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.tool_executor = tool_executor
        self.model = model
        self.max_turns = max_turns
        self.max_tokens = max_tokens
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
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                tools=self.tools,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                # Model stopped without calling finish_review. Most common
                # cause: response.stop_reason == "max_tokens" -- it ran out
                # of output budget mid-tool-call (e.g. the orchestrator
                # aggregating many specialists' findings into one big
                # finish_review payload) rather than actually choosing to
                # stop. Distinguish that from a genuine early stop so it's
                # diagnosable from the log instead of a silent empty result.
                if response.stop_reason == "max_tokens":
                    reason = (f"{self.name} ran out of output tokens (max_tokens={self.max_tokens}) "
                              f"before calling finish_review -- raise AGENT_MAX_TOKENS")
                else:
                    reason = f"{self.name} ended without finish_review (stop_reason={response.stop_reason})"
                print(f"[{self.name}] {reason}")
                final_result = {
                    "findings": [],
                    "summary": self._extract_text(response) or reason,
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
