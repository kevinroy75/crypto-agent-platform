"""
Unit tests for agent classes.

Tests BaseAgent, AgentResult, Tool, and the orchestration logic
using mocks for LLM API calls.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.base import AgentResult, BaseAgent, Tool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class DummyAgent(BaseAgent):
    """Concrete agent for testing purposes."""

    def _register_tools(self):
        self.add_tool(
            Tool(
                name="echo",
                description="Echo back the input",
                parameters={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                    },
                    "required": ["message"],
                },
                function=AsyncMock(return_value="echoed"),
            )
        )


@pytest.fixture
def agent() -> DummyAgent:
    return DummyAgent(
        name="test-agent",
        system_prompt="You are a test agent.",
        api_base="http://test:8080/v1",
        api_key="test-key",
    )


@pytest.fixture
def simple_llm_response() -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello from LLM",
                },
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }


@pytest.fixture
def tool_call_llm_response() -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_001",
                            "type": "function",
                            "function": {
                                "name": "echo",
                                "arguments": json.dumps({"message": "hi"}),
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"total_tokens": 20},
    }


# ---------------------------------------------------------------------------
# AgentResult tests
# ---------------------------------------------------------------------------

class TestAgentResult:
    def test_to_dict(self):
        result = AgentResult(
            output="test output",
            artifacts=["tool:search"],
            tokens_used=100,
            duration_ms=250,
            agent_name="test",
            metadata={"iterations": 1},
        )
        d = result.to_dict()
        assert d["output"] == "test output"
        assert d["artifacts"] == ["tool:search"]
        assert d["tokens_used"] == 100
        assert d["duration_ms"] == 250
        assert d["agent_name"] == "test"
        assert d["metadata"] == {"iterations": 1}

    def test_to_markdown(self):
        result = AgentResult(
            output="Analysis complete",
            artifacts=["tool:fetch_data", "tool:analyze"],
            tokens_used=50,
            duration_ms=100,
            agent_name="ResearchAgent",
        )
        md = result.to_markdown()
        assert "# ResearchAgent Result" in md
        assert "Analysis complete" in md
        assert "tool:fetch_data" in md
        assert "tool:analyze" in md
        assert "Tokens: 50" in md

    def test_defaults(self):
        result = AgentResult(output="bare minimum")
        assert result.artifacts == []
        assert result.tokens_used == 0
        assert result.duration_ms == 0
        assert result.agent_name == ""
        assert result.metadata == {}


# ---------------------------------------------------------------------------
# Tool tests
# ---------------------------------------------------------------------------

class TestTool:
    def test_to_schema(self):
        tool = Tool(
            name="search",
            description="Search the web",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "search"
        assert schema["function"]["description"] == "Search the web"
        assert "query" in schema["function"]["parameters"]["properties"]

    def test_tool_without_function(self):
        tool = Tool(
            name="placeholder",
            description="No implementation",
            parameters={"type": "object", "properties": {}},
        )
        assert tool.function is None


# ---------------------------------------------------------------------------
# BaseAgent tests
# ---------------------------------------------------------------------------

class TestBaseAgent:
    def test_initialization(self, agent: DummyAgent):
        assert agent.name == "test-agent"
        assert agent.system_prompt == "You are a test agent."
        assert len(agent.tools) == 1
        assert agent.tools[0].name == "echo"
        assert agent.conversation == []

    def test_add_tool(self, agent: DummyAgent):
        initial_count = len(agent.tools)
        new_tool = Tool(
            name="extra",
            description="An extra tool",
            parameters={"type": "object", "properties": {}},
        )
        agent.add_tool(new_tool)
        assert len(agent.tools) == initial_count + 1
        assert agent.tools[-1].name == "extra"

    def test_reset(self, agent: DummyAgent):
        agent.conversation = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        agent.reset()
        assert agent.conversation == []

    @pytest.mark.asyncio
    async def test_execute_tool_success(self, agent: DummyAgent):
        result = await agent._execute_tool("echo", {"message": "test"})
        assert result == "echoed"
        agent.tools[0].function.assert_called_once_with(message="test")

    @pytest.mark.asyncio
    async def test_execute_tool_unknown(self, agent: DummyAgent):
        result = await agent._execute_tool("nonexistent", {})
        assert "Unknown tool" in result

    @pytest.mark.asyncio
    async def test_execute_tool_error(self, agent: DummyAgent):
        agent.tools[0].function = AsyncMock(side_effect=ValueError("boom"))
        result = await agent._execute_tool("echo", {"message": "fail"})
        assert "Tool error" in result
        assert "boom" in result

    @pytest.mark.asyncio
    async def test_think_simple_response(self, agent: DummyAgent, simple_llm_response):
        with patch.object(agent, "_call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = simple_llm_response
            result = await agent.think("What is 2+2?")

        assert isinstance(result, AgentResult)
        assert result.output == "Hello from LLM"
        assert result.tokens_used == 15
        assert result.agent_name == "test-agent"
        assert result.duration_ms >= 0
        assert len(agent.conversation) == 2  # user + assistant

    @pytest.mark.asyncio
    async def test_think_with_tool_call(
        self, agent: DummyAgent, tool_call_llm_response, simple_llm_response
    ):
        with patch.object(agent, "_call_llm", new_callable=AsyncMock) as mock_call:
            # First call returns tool_call, second returns final text
            mock_call.side_effect = [tool_call_llm_response, simple_llm_response]
            result = await agent.think("Run the echo tool")

        assert result.output == "Hello from LLM"
        assert "tool:echo" in result.artifacts
        # user + tool_call + tool_result + assistant
        assert len(agent.conversation) == 4

    @pytest.mark.asyncio
    async def test_think_tool_then_response(self, agent: DummyAgent):
        tool_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_abc",
                                "type": "function",
                                "function": {
                                    "name": "echo",
                                    "arguments": '{"message": "ping"}',
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"total_tokens": 10},
        }
        final_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "The echo returned: echoed",
                    },
                }
            ],
            "usage": {"total_tokens": 12},
        }

        with patch.object(agent, "_call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = [tool_response, final_response]
            result = await agent.think("Please echo ping")

        assert "echoed" in result.output or "The echo" in result.output
        assert result.tokens_used == 22
        assert result.metadata["iterations"] == 2
