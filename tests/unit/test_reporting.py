"""Tests for reporting functionality."""

import json
from pathlib import Path

from rebuilder.reporting.json_output import write_rbvf_output


class TestWriteOutput:
    """Tests for write_rbvf_output function."""

    def test_write_creates_files(self, config, suite, tmp_path: Path):
        """Test that write creates output files."""
        output_path = write_rbvf_output(config, suite)

        assert output_path.exists()
        assert output_path.name == "stats.json"
        assert (output_path.parent / "packages.json").exists()
        assert (output_path.parent / "images.json").exists()

    def test_write_creates_directories(self, config, suite):
        """Test that write creates parent directories."""
        # Results dir shouldn't exist yet
        assert not config.results_dir.exists()

        write_rbvf_output(config, suite)

        assert config.results_dir.exists()

    def test_write_valid_json(self, config, suite):
        """Test that output is valid JSON."""
        output_path = write_rbvf_output(config, suite)

        # Should not raise
        stats = json.loads(output_path.read_text())
        packages = json.loads((output_path.parent / "packages.json").read_text())
        images = json.loads((output_path.parent / "images.json").read_text())

        assert stats["version"] == config.version
        assert stats["target"] == config.target
        assert isinstance(packages, list)
        assert isinstance(images, list)

    def test_write_custom_path(self, config, suite, tmp_path: Path):
        """Test writing to custom path."""
        custom_path = tmp_path / "custom" / "results.json"

        output_path = write_rbvf_output(config, suite, custom_path)

        # Returns stats.json in the parent directory
        assert output_path.parent == custom_path.parent
        assert output_path.exists()

    def test_write_with_populated_suite(self, config, populated_suite):
        """Test writing with populated suite."""
        output_path = write_rbvf_output(config, populated_suite)

        stats = json.loads(output_path.read_text())
        packages = json.loads((output_path.parent / "packages.json").read_text())
        images = json.loads((output_path.parent / "images.json").read_text())

        # Check stats
        assert stats["packages"]["good"] == 3
        assert stats["packages"]["bad"] == 1
        assert stats["images"]["good"] == 1

        # Check packages list (3 good + 1 bad + 1 unknown = 5)
        assert len(packages) == 5
        assert len(images) == 1
