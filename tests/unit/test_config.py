"""Tests for configuration management."""

from pathlib import Path

import pytest

from rebuilder.config import Config


class TestConfig:
    """Tests for Config dataclass."""

    def test_default_config(self, tmp_path: Path):
        """Test creating config with defaults."""
        config = Config(
            rebuild_dir=tmp_path / "build",
            dl_dir=tmp_path / "dl",
            results_dir=tmp_path / "results",
        )
        assert config.target == "x86/64"
        assert config.version == "SNAPSHOT"
        assert config.jobs >= 1

    def test_config_with_custom_values(self, tmp_path: Path):
        """Test creating config with custom values."""
        config = Config(
            target="mediatek/filogic",
            version="23.05.2",
            rebuild_dir=tmp_path / "build",
            dl_dir=tmp_path / "dl",
            results_dir=tmp_path / "results",
            jobs=4,
        )
        assert config.target == "mediatek/filogic"
        assert config.version == "23.05.2"
        assert config.jobs == 4

    def test_bin_path(self, config: Config):
        """Test bin_path property."""
        assert config.bin_path == config.rebuild_dir / "bin"

    def test_release_dir_snapshot(self, config: Config):
        """Test release_dir for SNAPSHOT."""
        assert config.release_dir == "snapshots"

    def test_release_dir_version(self, tmp_path: Path):
        """Test release_dir for versioned release."""
        config = Config(
            version="23.05.2",
            rebuild_dir=tmp_path / "build",
            dl_dir=tmp_path / "dl",
            results_dir=tmp_path / "results",
        )
        assert config.release_dir == "releases/23.05.2"

    def test_target_dir(self, config: Config):
        """Test target_dir property."""
        assert config.target_dir == "snapshots/targets/x86/64"

    def test_branch_snapshot(self, config: Config):
        """Test branch for SNAPSHOT."""
        assert config.branch == "master"

    def test_branch_version(self, tmp_path: Path):
        """Test branch for versioned release."""
        config = Config(
            version="23.05.2",
            rebuild_dir=tmp_path / "build",
            dl_dir=tmp_path / "dl",
            results_dir=tmp_path / "results",
        )
        assert config.branch == "openwrt-23.05"

    def test_branch_version_single_digit_minor(self, tmp_path: Path):
        """Test branch parsing for versions like 24.10.0."""
        config = Config(
            version="24.10.0",
            rebuild_dir=tmp_path / "build",
            dl_dir=tmp_path / "dl",
            results_dir=tmp_path / "results",
        )
        assert config.branch == "openwrt-24.10"


class TestConfigValidation:
    """Tests for configuration validation."""

    def test_valid_config(self, config: Config):
        """Test validation passes for valid config."""
        errors = config.validate()
        assert len(errors) == 0

    def test_invalid_target_format(self, tmp_path: Path):
        """Test validation catches invalid target format."""
        config = Config(
            target="x86",  # Missing subtarget
            rebuild_dir=tmp_path / "build",
            dl_dir=tmp_path / "dl",
            results_dir=tmp_path / "results",
        )
        errors = config.validate()
        assert len(errors) == 1
        assert "Invalid target format" in errors[0]

    def test_invalid_origin_url(self, tmp_path: Path):
        """Test validation catches invalid origin URL."""
        config = Config(
            origin_url="not-a-url",
            rebuild_dir=tmp_path / "build",
            dl_dir=tmp_path / "dl",
            results_dir=tmp_path / "results",
        )
        errors = config.validate()
        assert len(errors) == 1
        assert "Invalid origin URL" in errors[0]

    def test_invalid_jobs(self, tmp_path: Path):
        """Test validation catches invalid job count."""
        config = Config(
            jobs=0,
            rebuild_dir=tmp_path / "build",
            dl_dir=tmp_path / "dl",
            results_dir=tmp_path / "results",
        )
        errors = config.validate()
        assert len(errors) == 1
        assert "Invalid job count" in errors[0]

    def test_multiple_validation_errors(self, tmp_path: Path):
        """Test validation catches multiple errors."""
        config = Config(
            target="invalid",
            origin_url="bad",
            jobs=-1,
            rebuild_dir=tmp_path / "build",
            dl_dir=tmp_path / "dl",
            results_dir=tmp_path / "results",
        )
        errors = config.validate()
        assert len(errors) == 3
