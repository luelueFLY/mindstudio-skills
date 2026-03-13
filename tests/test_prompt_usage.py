from pathlib import Path

from msagent.cli.core.context import Context
from msagent.cli.ui.prompt import InteractivePrompt
from msagent.configs import ApprovalMode


def _build_prompt_context(**overrides) -> Context:
    data = {
        "agent": "general",
        "model": "default",
        "thread_id": "thread-1",
        "working_dir": Path.cwd(),
        "approval_mode": ApprovalMode.SEMI_ACTIVE,
        "recursion_limit": 80,
        "current_input_tokens": 6000,
        "current_output_tokens": 2000,
        "context_window": 64000,
    }
    data.update(overrides)
    return Context(**data)


def test_prompt_usage_info_shows_ctx_and_token_breakdown() -> None:
    prompt = InteractivePrompt.__new__(InteractivePrompt)
    prompt.context = _build_prompt_context()

    usage = prompt._build_usage_info()

    assert usage == "  [ctx 8K/64K tokens (13%) | in 6K | out 2K]"
    assert "$" not in usage


def test_prompt_usage_info_is_hidden_without_input_tokens() -> None:
    prompt = InteractivePrompt.__new__(InteractivePrompt)
    prompt.context = _build_prompt_context(current_input_tokens=None)

    assert prompt._build_usage_info() == ""


def test_placeholder_text_uses_msagent_prompt_and_hints() -> None:
    prompt = InteractivePrompt.__new__(InteractivePrompt)
    prompt.context = _build_prompt_context()

    text = prompt._build_placeholder_text()

    assert text == "尽管问msAgent，试试 /命令 或 @文件  [ctx 8K/64K tokens (13%) | in 6K | out 2K]"
    assert "general:default" not in text
