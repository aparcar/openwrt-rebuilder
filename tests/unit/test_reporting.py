"""Tests for reporting functionality."""

import json
from pathlib import Path

import pytest

from rebuilder.reporting.json_output import (
    load_rbvf_output,
    merge_rbvf_outputs,
    write_rbvf_output,
)


@pytest.fixture
def sample_rbvf_data() -> dict:
    """Sample RBVF output data."""
    return {
        "SNAPSHOT": {
            "x86/64": {
                "packages": {
                    "reproducible": [
                        {
                            "name": "base-files",
                            "version": "1.0",
                            "arch": "x86_64",
                            "distribution": "openwrt",
                            "status": "reproducible",
                            "files": {"reproducible": ["packages/base-files-1.0.ipk"]},
                        }
                    ],
                    "unreproducible": [],
                    "notfound": [],
                    "pending": [],
                },
                "images": {
                    "reproducible": [],
                    "unreproducible": [],
                    "notfound": [],
                    "pending": [],
                },
            }
        }
    }


class TestJsonOutput:
    """Tests for JSON output functions."""

    def test_load_rbvf_output(self, tmp_path: Path, sample_rbvf_data: dict):
        """Test loading RBVF output from file."""
        output_file = tmp_path / "output.json"
        output_file.write_text(json.dumps(sample_rbvf_data))

        loaded = load_rbvf_output(output_file)
        assert loaded == sample_rbvf_data

    def test_merge_rbvf_outputs_single(self, sample_rbvf_data: dict):
        """Test merging a single output."""
        merged = merge_rbvf_outputs([sample_rbvf_data])
        assert merged == sample_rbvf_data

    def test_merge_rbvf_outputs_multiple_versions(self):
        """Test merging outputs with different versions."""
        output1 = {
            "SNAPSHOT": {"x86/64": {"packages": {"reproducible": []}, "images": {}}}
        }
        output2 = {
            "23.05.2": {"x86/64": {"packages": {"reproducible": []}, "images": {}}}
        }

        merged = merge_rbvf_outputs([output1, output2])

        assert "SNAPSHOT" in merged
        assert "23.05.2" in merged

    def test_merge_rbvf_outputs_multiple_targets(self):
        """Test merging outputs with different targets."""
        output1 = {
            "SNAPSHOT": {"x86/64": {"packages": {}, "images": {}}}
        }
        output2 = {
            "SNAPSHOT": {"mediatek/filogic": {"packages": {}, "images": {}}}
        }

        merged = merge_rbvf_outputs([output1, output2])

        assert "x86/64" in merged["SNAPSHOT"]
        assert "mediatek/filogic" in merged["SNAPSHOT"]

    def test_merge_rbvf_outputs_empty(self):
        """Test merging empty list."""
        merged = merge_rbvf_outputs([])
        assert merged == {}


class TestWriteRbvfOutput:
    """Tests for write_rbvf_output function."""

    def test_write_creates_file(self, config, suite, tmp_path: Path):
        """Test that write creates output file."""
        output_path = write_rbvf_output(config, suite)

        assert output_path.exists()
        assert output_path.name == "output.json"

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
        data = json.loads(output_path.read_text())

        assert config.version in data
        assert config.target in data[config.version]

    def test_write_custom_path(self, config, suite, tmp_path: Path):
        """Test writing to custom path."""
        custom_path = tmp_path / "custom" / "results.json"

        output_path = write_rbvf_output(config, suite, custom_path)

        assert output_path == custom_path
        assert custom_path.exists()

    def test_write_with_populated_suite(self, config, populated_suite):
        """Test writing with populated suite."""
        output_path = write_rbvf_output(config, populated_suite)

        data = json.loads(output_path.read_text())
        target_data = data[config.version][config.target]

        assert len(target_data["packages"]["reproducible"]) == 3
        assert len(target_data["packages"]["unreproducible"]) == 1
        assert len(target_data["images"]["reproducible"]) == 1
