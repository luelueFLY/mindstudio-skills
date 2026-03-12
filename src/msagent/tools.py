"""Tool abstractions and built-in tools for msagent."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


ToolHandler = Callable[[dict[str, Any]], Awaitable[str]]


class ToolProvider(Protocol):
    """Provider interface for exposing and executing tools."""

    def get_tools(self) -> list[dict[str, Any]]: ...

    def supports(self, full_tool_name: str) -> bool: ...

    async def call_tool(self, full_tool_name: str, arguments: dict[str, Any]) -> str: ...


class MCPManagerLike(Protocol):
    """Subset of MCP manager behavior needed by the tool layer."""

    def get_all_tools(self) -> list[dict[str, Any]]: ...

    async def call_tool(self, full_tool_name: str, arguments: dict[str, Any]) -> str: ...


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """A local tool definition with schema + async handler."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class BuiltinToolRegistry:
    """Registry for built-in tools shipped with msagent."""

    def __init__(self, definitions: Iterable[ToolDefinition]):
        self._definitions = {definition.name: definition for definition in definitions}

    def get_tools(self) -> list[dict[str, Any]]:
        return [definition.to_openai_schema() for definition in self._definitions.values()]

    def supports(self, full_tool_name: str) -> bool:
        return full_tool_name in self._definitions

    async def call_tool(self, full_tool_name: str, arguments: dict[str, Any]) -> str:
        definition = self._definitions.get(full_tool_name)
        if definition is None:
            return f"Error: Tool '{full_tool_name}' not found"
        return await definition.handler(arguments)


class MCPToolProvider:
    """Adapter that makes the MCP manager conform to ToolProvider."""

    def __init__(self, manager: MCPManagerLike):
        self._manager = manager

    def get_tools(self) -> list[dict[str, Any]]:
        return self._manager.get_all_tools()

    def supports(self, full_tool_name: str) -> bool:
        return any(self._tool_name(tool) == full_tool_name for tool in self.get_tools())

    async def call_tool(self, full_tool_name: str, arguments: dict[str, Any]) -> str:
        return await self._manager.call_tool(full_tool_name, arguments)

    def _tool_name(self, tool_spec: dict[str, Any]) -> str:
        function = tool_spec.get("function")
        if not isinstance(function, dict):
            return ""
        name = function.get("name")
        return name if isinstance(name, str) else ""


class CompositeToolInvoker:
    """Composite provider that aggregates tool discovery and dispatch."""

    def __init__(self, providers: Iterable[ToolProvider]):
        self._providers = list(providers)

    def get_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        seen: set[str] = set()

        for provider in self._providers:
            for tool in provider.get_tools():
                tool_name = self._extract_tool_name(tool)
                if not tool_name or tool_name in seen:
                    continue
                seen.add(tool_name)
                tools.append(tool)
        return tools

    async def call_tool(self, full_tool_name: str, arguments: dict[str, Any]) -> str:
        for provider in self._providers:
            if provider.supports(full_tool_name):
                return await provider.call_tool(full_tool_name, arguments)
        return f"Error: Tool '{full_tool_name}' not found"

    def _extract_tool_name(self, tool_spec: dict[str, Any]) -> str:
        function = tool_spec.get("function")
        if not isinstance(function, dict):
            return ""
        name = function.get("name")
        return name if isinstance(name, str) else ""


@dataclass(frozen=True, slots=True)
class PythonExecutionSettings:
    """Runtime settings for the built-in Python execution tool."""

    interpreter: str
    default_timeout_s: float
    max_timeout_s: float
    max_output_chars: int

    @classmethod
    def from_env(cls) -> PythonExecutionSettings:
        default_timeout = _read_env_float("MSAGENT_PYTHON_TOOL_TIMEOUT", 30.0)
        max_timeout = _read_env_float("MSAGENT_PYTHON_TOOL_MAX_TIMEOUT", 120.0)
        if max_timeout <= 0:
            max_timeout = 120.0
        if default_timeout <= 0:
            default_timeout = min(30.0, max_timeout)
        default_timeout = min(default_timeout, max_timeout)

        return cls(
            interpreter=sys.executable,
            default_timeout_s=default_timeout,
            max_timeout_s=max_timeout,
            max_output_chars=_read_env_int("MSAGENT_PYTHON_TOOL_OUTPUT_LIMIT", 12000),
        )


class PythonCodeExecutor:
    """Executes generated Python code through a temporary script subprocess."""

    TOOL_NAME = "builtin__execute_python"
    _TEMP_DIR_PREFIX = "msagent-python-tool-"
    _SCRIPT_NAME = "snippet.py"
    _TERMINATION_GRACE_S = 5.0

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        settings: PythonExecutionSettings | None = None,
        temp_root: str | Path | None = None,
    ):
        self._workspace_root = Path(workspace_root).expanduser().resolve()
        self._settings = settings or PythonExecutionSettings.from_env()
        self._temp_root = (
            Path(temp_root).expanduser().resolve() if temp_root is not None else None
        )

    async def handle_tool_call(self, arguments: dict[str, Any]) -> str:
        code = arguments.get("code")
        timeout_seconds = arguments.get("timeout_seconds")
        return await self.execute(code=code, timeout_seconds=timeout_seconds)

    async def execute(self, code: Any, timeout_seconds: Any = None) -> str:
        try:
            normalized_code = self._normalize_code(code)
            timeout_s = self._resolve_timeout(timeout_seconds)
        except ValueError as exc:
            return self._serialize_result(
                ok=False,
                error_type="validation_error",
                error=str(exc),
                exit_code=None,
                stdout="",
                stderr="",
                timed_out=False,
                duration_seconds=0.0,
            )

        start = time.monotonic()
        process = None

        try:
            with tempfile.TemporaryDirectory(
                prefix=self._TEMP_DIR_PREFIX,
                dir=self._temp_root,
            ) as temp_dir:
                script_path = Path(temp_dir) / self._SCRIPT_NAME
                script_path.write_text(normalized_code, encoding="utf-8")

                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"
                env.setdefault("PYTHONIOENCODING", "utf-8")

                process = await asyncio.create_subprocess_exec(
                    self._settings.interpreter,
                    "-u",
                    script_path.as_posix(),
                    cwd=self._workspace_root.as_posix(),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        process.communicate(),
                        timeout=timeout_s,
                    )
                except asyncio.TimeoutError:
                    stdout_bytes, stderr_bytes = await self._terminate_process(process)
                    duration = time.monotonic() - start
                    stdout, stdout_truncated = self._truncate_output(
                        self._decode_output(stdout_bytes)
                    )
                    stderr, stderr_truncated = self._truncate_output(
                        self._decode_output(stderr_bytes)
                    )
                    return self._serialize_result(
                        ok=False,
                        error_type="timeout",
                        error=f"Execution timed out after {timeout_s:.2f}s",
                        exit_code=process.returncode,
                        stdout=stdout,
                        stderr=stderr,
                        timed_out=True,
                        duration_seconds=duration,
                        stdout_truncated=stdout_truncated,
                        stderr_truncated=stderr_truncated,
                    )

                duration = time.monotonic() - start
                stdout, stdout_truncated = self._truncate_output(
                    self._decode_output(stdout_bytes)
                )
                stderr, stderr_truncated = self._truncate_output(
                    self._decode_output(stderr_bytes)
                )
                exit_code = process.returncode
                ok = exit_code == 0

                return self._serialize_result(
                    ok=ok,
                    error_type=None if ok else "process_exit",
                    error=None if ok else f"Python exited with code {exit_code}",
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    timed_out=False,
                    duration_seconds=duration,
                    stdout_truncated=stdout_truncated,
                    stderr_truncated=stderr_truncated,
                )
        except Exception as exc:
            duration = time.monotonic() - start
            return self._serialize_result(
                ok=False,
                error_type="execution_error",
                error=str(exc),
                exit_code=getattr(process, "returncode", None),
                stdout="",
                stderr="",
                timed_out=False,
                duration_seconds=duration,
            )

    async def _terminate_process(
        self, process: asyncio.subprocess.Process
    ) -> tuple[bytes, bytes]:
        try:
            if process.returncode is None:
                process.terminate()
        except ProcessLookupError:
            pass

        try:
            return await asyncio.wait_for(
                process.communicate(),
                timeout=self._TERMINATION_GRACE_S,
            )
        except asyncio.TimeoutError:
            try:
                if process.returncode is None:
                    process.kill()
            except ProcessLookupError:
                pass
            try:
                return await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._TERMINATION_GRACE_S,
                )
            except Exception:
                return b"", b""

    def _normalize_code(self, code: Any) -> str:
        if not isinstance(code, str):
            raise ValueError("`code` must be a string")
        if not code.strip():
            raise ValueError("`code` must not be empty")
        return code

    def _resolve_timeout(self, timeout_seconds: Any) -> float:
        if timeout_seconds is None:
            return self._settings.default_timeout_s

        try:
            resolved = float(timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("`timeout_seconds` must be a positive number") from exc

        if resolved <= 0:
            raise ValueError("`timeout_seconds` must be a positive number")
        return min(resolved, self._settings.max_timeout_s)

    def _decode_output(self, payload: bytes | None) -> str:
        if not payload:
            return ""
        return payload.decode("utf-8", errors="replace")

    def _truncate_output(self, text: str) -> tuple[str, bool]:
        limit = max(1, self._settings.max_output_chars)
        if len(text) <= limit:
            return text, False
        truncated = text[:limit]
        return f"{truncated}\n...[truncated]...", True

    def _serialize_result(
        self,
        *,
        ok: bool,
        error_type: str | None,
        error: str | None,
        exit_code: int | None,
        stdout: str,
        stderr: str,
        timed_out: bool,
        duration_seconds: float,
        stdout_truncated: bool = False,
        stderr_truncated: bool = False,
    ) -> str:
        payload: dict[str, Any] = {
            "ok": ok,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "duration_seconds": round(duration_seconds, 3),
        }
        if error_type is not None:
            payload["error_type"] = error_type
        if error is not None:
            payload["error"] = error
        if stdout_truncated:
            payload["stdout_truncated"] = True
        if stderr_truncated:
            payload["stderr_truncated"] = True
        return json.dumps(payload, ensure_ascii=False, indent=2)


def create_builtin_tool_registry(workspace_root: str | Path) -> BuiltinToolRegistry:
    """Create the built-in tool registry available to the agent."""
    executor = PythonCodeExecutor(workspace_root)
    return BuiltinToolRegistry(
        [
            ToolDefinition(
                name=PythonCodeExecutor.TOOL_NAME,
                description=(
                    "Execute Python 3 code inside the workspace using a temporary script. "
                    "Use this for calculations, parsing data, inspecting files, or running "
                    "short repository-aware automation. Returns JSON with success flag, "
                    "exit code, stdout, stderr, timeout info, and duration."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Complete Python script to execute.",
                        },
                        "timeout_seconds": {
                            "type": "number",
                            "description": (
                                "Optional timeout in seconds. Values above the system limit "
                                "will be capped."
                            ),
                        },
                    },
                    "required": ["code"],
                },
                handler=executor.handle_tool_call,
            )
        ]
    )


def create_tool_invoker(
    workspace_root: str | Path,
    mcp_manager: MCPManagerLike,
) -> CompositeToolInvoker:
    """Create the shared tool invoker used by Agent and LLM layers."""
    return CompositeToolInvoker(
        [
            create_builtin_tool_registry(workspace_root),
            MCPToolProvider(mcp_manager),
        ]
    )


def _read_env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _read_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default
