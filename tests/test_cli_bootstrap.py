from msagent.cli.bootstrap.app import create_parser
from msagent.cli.bootstrap.legacy import (
    DEFAULT_SESSION_COMMAND,
    create_session_parser,
    normalize_argv,
)
from msagent.core.constants import APP_NAME


def test_create_session_parser_defaults_to_interactive_mode() -> None:
    parser = create_session_parser()
    args = parser.parse_args([])

    assert parser.prog == APP_NAME == "msagent"
    assert args.message is None
    assert args.cli_command == DEFAULT_SESSION_COMMAND
    assert args.resume is False
    assert args.stream is True


def test_normalize_argv_routes_messages_to_default_session() -> None:
    assert normalize_argv(["hello"]) == [DEFAULT_SESSION_COMMAND, "hello"]
    assert normalize_argv(["config", "--show"]) == ["config", "--show"]


def test_help_only_exposes_config_command() -> None:
    parser = create_parser()
    help_text = parser.format_help()

    assert "config" in help_text
    assert DEFAULT_SESSION_COMMAND not in help_text
    assert "chat" not in help_text
    assert "ask" not in help_text
    assert "mcp" not in help_text
    assert "server" not in help_text
