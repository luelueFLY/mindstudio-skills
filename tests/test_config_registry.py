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

    general_agent = yaml.safe_load((config_dir / "agents" / "general.yml").read_text())
    assert "impl:file_system:ls" in general_agent["tools"]["patterns"]
    assert "impl:file_system:glob" in general_agent["tools"]["patterns"]
