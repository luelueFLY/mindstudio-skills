from pathlib import Path
import json
import yaml

import pytest

from msagent.configs.registry import ConfigRegistry


@pytest.mark.asyncio
async def test_config_registry_bootstraps_default_layout(tmp_path: Path) -> None:
    registry = ConfigRegistry(tmp_path)

    await registry.ensure_config_dir()

    config_dir = tmp_path / ".msagent"
    assert config_dir.exists()
    assert (config_dir / "README.md").exists()
    assert (config_dir / "agents").is_dir()
    assert (config_dir / "llms").is_dir()
    assert (config_dir / "sandboxes").is_dir()
    assert (config_dir / "subagents").is_dir()
    assert (config_dir / "config.llms.yml").exists()
    assert (config_dir / "config.mcp.json").exists()

    mcp_config = json.loads((config_dir / "config.mcp.json").read_text())
    assert "msprof-mcp" in mcp_config["mcpServers"]
    msprof_server = mcp_config["mcpServers"]["msprof-mcp"]
    assert "--refresh" not in msprof_server["args"]
    assert msprof_server["stateful"] is True

    msagent = yaml.safe_load((config_dir / "agents" / "msagent.yml").read_text())
    assert "impl:file_system:*" in msagent["tools"]["patterns"]
    assert "mcp:*:*" in msagent["tools"]["patterns"]


@pytest.mark.asyncio
async def test_config_registry_normalizes_legacy_msprof_mcp_defaults(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / ".msagent"
    config_dir.mkdir(parents=True)
    legacy_mcp = {
        "mcpServers": {
            "msprof-mcp": {
                "command": "uvx",
                "args": [
                    "--isolated",
                    "--refresh",
                    "--from",
                    "git+https://gitcode.com/kali20gakki1/msprof_mcp.git",
                    "msprof-mcp",
                ],
                "transport": "stdio",
                "env": {},
                "include": [],
                "exclude": [],
                "enabled": False,
                "stateful": False,
            }
        }
    }
    (config_dir / "config.mcp.json").write_text(
        json.dumps(legacy_mcp, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    registry = ConfigRegistry(tmp_path)

    await registry.ensure_config_dir()

    mcp_config = json.loads((config_dir / "config.mcp.json").read_text(encoding="utf-8"))
    msprof_server = mcp_config["mcpServers"]["msprof-mcp"]
    assert "--refresh" not in msprof_server["args"]
    assert msprof_server["stateful"] is True
    assert msprof_server["enabled"] is False
