"""
Base agent class with LLM integration and tool-use capabilities.
"""
import json
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Result from an agent execution."""
    output: str
    artifacts: list[str] = field(default_factory=list)
    tokens_used: int = 0
    duration_ms: int = 0
    agent_name: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "output": self.output,
            "artifacts": self.artifacts,
            "tokens_used": self.tokens_used,
            "duration_ms": self.duration_ms,
            "agent_name": self.agent_name,
            "metadata": self.metadata,
        }

    def to_markdown(self) -> str:
        lines = [f"# {self.agent_name} Result\n"]
        lines.append(self.output)
        if self.artifacts:
            lines.append("\n## Artifacts\n")
            for a in self.artifacts:
                lines.append(f"- {a}")
        lines.append(f"\n---\n*Tokens: {self.tokens_used} | Duration: {self.duration_ms}ms*")
        return "\n".join(lines)


@dataclass
class Tool:
    """Tool definition for agent tool-use."""
    name: str
    description: str
    parameters: dict[str, Any]
    function: Any = None

    def to_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class BaseAgent(ABC):
    """Base class for all agents with LLM-powered reasoning and tool execution."""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        model: str = "mimo-v2.5-pro",
        api_base: str = "http://localhost:8080/v1",
        api_key: str = "sk-placeholder",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        verbose: bool = False,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.model = model
        self.api_base = api_base
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.verbose = verbose
        self.tools: list[Tool] = []
        self.conversation: list[dict] = []
        self._register_tools()

    @abstractmethod
    def _register_tools(self):
        """Register tools available to this agent."""
        pass

    def add_tool(self, tool: Tool):
        self.tools.append(tool)

    async def _call_llm(self, messages: list[dict]) -> dict:
        """Call the LLM API with messages and optional tool schemas."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if self.tools:
            payload["tools"] = [t.to_schema() for t in self.tools]
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.api_base}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool by name with given arguments."""
        for tool in self.tools:
            if tool.name == tool_name:
                if self.verbose:
                    logger.info(f"[{self.name}] Executing tool: {tool_name}({arguments})")
                try:
                    result = await tool.function(**arguments) if tool.function else "Tool not implemented"
                    return str(result)
                except Exception as e:
                    return f"Tool error: {e}"
        return f"Unknown tool: {tool_name}"

    async def think(self, user_message: str) -> AgentResult:
        """
        Main reasoning loop: send message to LLM, execute tools, iterate until done.
        Implements the ReAct pattern (Reason + Act).
        """
        start = time.time()
        self.conversation.append({"role": "user", "content": user_message})

        if self.verbose:
            logger.info(f"[{self.name}] Processing: {user_message[:100]}...")

        total_tokens = 0
        artifacts = []
        max_iterations = 10

        for iteration in range(max_iterations):
            response = await self._call_llm(
                [{"role": "system", "content": self.system_prompt}] + self.conversation
            )

            choice = response["choices"][0]
            message = choice["message"]
            usage = response.get("usage", {})
            total_tokens += usage.get("total_tokens", 0)

            # Check if LLM wants to use tools
            if message.get("tool_calls"):
                self.conversation.append(message)

                for tool_call in message["tool_calls"]:
                    fn = tool_call["function"]
                    args = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
                    result = await self._execute_tool(fn["name"], args)

                    self.conversation.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result,
                    })

                    artifacts.append(f"tool:{fn['name']}")

            elif message.get("content"):
                # LLM produced a final text response
                self.conversation.append({"role": "assistant", "content": message["content"]})

                duration = int((time.time() - start) * 1000)
                return AgentResult(
                    output=message["content"],
                    artifacts=artifacts,
                    tokens_used=total_tokens,
                    duration_ms=duration,
                    agent_name=self.name,
                    metadata={"iterations": iteration + 1},
                )

        # Max iterations reached
        duration = int((time.time() - start) * 1000)
        return AgentResult(
            output="Agent reached maximum reasoning iterations without a final answer.",
            artifacts=artifacts,
            tokens_used=total_tokens,
            duration_ms=duration,
            agent_name=self.name,
            metadata={"iterations": max_iterations, "status": "max_iterations"},
        )

    def reset(self):
        """Clear conversation history."""
        self.conversation.clear()
