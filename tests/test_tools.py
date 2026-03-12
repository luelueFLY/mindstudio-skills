"""Tests for tool abstractions and built-in Python execution tool."""

from __future__ import annotations

import json
import sys

import pytest

from msagent.tools import (
    BuiltinToolRegistry,
    CompositeToolInvoker,
    PythonCodeExecutor,
    PythonExecutionSettings,
    ToolDefinition,
)


class StubProvider:
    def __init__(self, tools: list[dict], response: str = "ok") -> None:
        self._tools = tools
        self._response = response
        self.calls: list[tuple[str, dict]] = []

    def get_tools(self) -> list[dict]:
        return self._tools

    def supports(self, full_tool_name: str) -> bool:
        return any(tool["function"]["name"] == full_tool_name for tool in self._tools)

    async def call_tool(self, full_tool_name: str, arguments: dict) -> str:
        self.calls.append((full_tool_name, arguments))
        return self._response


@pytest.mark.asyncio
async def test_python_code_executor_runs_code_and_cleans_temp_files(
    tmp_path,
) -> None:
    executor = PythonCodeExecutor(
        workspace_root=tmp_path,
        temp_root=tmp_path,
        settings=PythonExecutionSettings(
            interpreter=sys.executable,
            default_timeout_s=2.0,
            max_timeout_s=2.0,
            max_output_chars=1000,
        ),
    )

    raw = await executor.execute("print('hello from tool')")
    payload = json.loads(raw)

    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert payload["stdout"].strip() == "hello from tool"
    assert payload["stderr"] == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_python_code_executor_reports_script_exception(tmp_path) -> None:
    executor = PythonCodeExecutor(workspace_root=tmp_path)

    raw = await executor.execute("raise RuntimeError('boom')")
    payload = json.loads(raw)

    assert payload["ok"] is False
    assert payload["error_type"] == "process_exit"
    assert payload["exit_code"] != 0
    assert "RuntimeError: boom" in payload["stderr"]


@pytest.mark.asyncio
async def test_python_code_executor_handles_timeout(tmp_path) -> None:
    executor = PythonCodeExecutor(
        workspace_root=tmp_path,
        settings=PythonExecutionSettings(
            interpreter=sys.executable,
            default_timeout_s=0.1,
            max_timeout_s=0.2,
            max_output_chars=1000,
        ),
    )

    raw = await executor.execute("import time\ntime.sleep(5)", timeout_seconds=0.1)
    payload = json.loads(raw)

    assert payload["ok"] is False
    assert payload["timed_out"] is True
    assert payload["error_type"] == "timeout"


@pytest.mark.asyncio
async def test_python_code_executor_rejects_empty_code(tmp_path) -> None:
    executor = PythonCodeExecutor(workspace_root=tmp_path)

    raw = await executor.execute("   ")
    payload = json.loads(raw)

    assert payload["ok"] is False
    assert payload["error_type"] == "validation_error"


@pytest.mark.asyncio
async def test_composite_tool_invoker_deduplicates_and_routes() -> None:
    builtin = StubProvider(
        [
            {
                "type": "function",
                "function": {"name": "builtin__execute_python"},
            }
        ],
        response="builtin-response",
    )
    mcp = StubProvider(
        [
            {
                "type": "function",
                "function": {"name": "mcp__search"},
            },
            {
                "type": "function",
                "function": {"name": "builtin__execute_python"},
            },
        ],
        response="mcp-response",
    )
    invoker = CompositeToolInvoker([builtin, mcp])

    assert [tool["function"]["name"] for tool in invoker.get_tools()] == [
        "builtin__execute_python",
        "mcp__search",
    ]

    response = await invoker.call_tool("builtin__execute_python", {"code": "print(1)"})

    assert response == "builtin-response"
    assert builtin.calls == [("builtin__execute_python", {"code": "print(1)"})]
    assert mcp.calls == []


@pytest.mark.asyncio
async def test_builtin_tool_registry_invokes_registered_handler() -> None:
    async def _handler(arguments: dict) -> str:
        return f"handled:{arguments['value']}"

    registry = BuiltinToolRegistry(
        [
            ToolDefinition(
                name="builtin__echo",
                description="Echo test tool",
                parameters={"type": "object", "properties": {"value": {"type": "string"}}},
                handler=_handler,
            )
        ]
    )

    response = await registry.call_tool("builtin__echo", {"value": "x"})

    assert registry.supports("builtin__echo") is True
    assert registry.get_tools()[0]["function"]["name"] == "builtin__echo"
    assert response == "handled:x"
