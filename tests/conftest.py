"""Pytest fixtures and configuration."""

from pathlib import Path

import pytest

from rebuilder.config import Config


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """Create a test configuration."""
    return Config(
        target="x86/64",
        version="SNAPSHOT",
        rebuild_dir=tmp_path / "build",
        dl_dir=tmp_path / "dl",
        results_dir=tmp_path / "results",
        origin_url="https://downloads.openwrt.org",
        source_mirror="https://codeberg.org/openwrt/",
        jobs=2,
    )
