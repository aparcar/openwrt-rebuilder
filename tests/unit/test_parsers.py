"""Tests for file parsers."""

import json
from pathlib import Path

import pytest

from rebuilder.parsers.packages import PackageIndex, parse_packages, parse_packages_file
from rebuilder.parsers.profiles import parse_profiles, parse_profiles_file
from rebuilder.parsers.sha256sums import parse_sha256sums, parse_sha256sums_file


class TestSha256sumsParser:
    """Tests for SHA256 checksum parsing."""

    def test_parse_simple(self, sample_sha256sums: str):
        """Test parsing simple sha256sums file."""
        result = parse_sha256sums(sample_sha256sums)
        assert len(result) == 3
        assert "foo-1.0.0.ipk" in result
        assert result["foo-1.0.0.ipk"] == "abc123def456789012345678901234567890123456789012345678901234"

    def test_parse_extracts_filename(self):
        """Test that only filename is extracted, not full path."""
        content = "abc123def456789012345678901234567890123456789012345678901234 *some/deep/path/file.ipk\n"
        result = parse_sha256sums(content)
        assert "file.ipk" in result
        assert "some/deep/path/file.ipk" not in result

    def test_parse_empty_content(self):
        """Test parsing empty content."""
        result = parse_sha256sums("")
        assert len(result) == 0

    def test_parse_ignores_invalid_lines(self):
        """Test that invalid lines are ignored."""
        content = """abc123def456789012345678901234567890123456789012345678901234 *valid.ipk
not a valid line
def456abc789012345678901234567890123456789012345678901234567 *another.ipk
"""
        result = parse_sha256sums(content)
        assert len(result) == 2
        assert "valid.ipk" in result
        assert "another.ipk" in result

    def test_parse_file(self, tmp_path: Path, sample_sha256sums: str):
        """Test parsing from file."""
        file_path = tmp_path / "sha256sums"
        file_path.write_text(sample_sha256sums)

        result = parse_sha256sums_file(file_path)
        assert len(result) == 3

    def test_parse_file_not_found(self, tmp_path: Path):
        """Test parsing nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            parse_sha256sums_file(tmp_path / "nonexistent")


class TestProfilesParser:
    """Tests for profiles.json parsing."""

    def test_parse_profiles(self, sample_profiles_json: str):
        """Test parsing profiles.json."""
        result = parse_profiles(sample_profiles_json)
        assert len(result) == 2
        assert "openwrt-x86-64-generic-squashfs-combined.img.gz" in result

    def test_parse_empty_profiles(self):
        """Test parsing empty profiles."""
        result = parse_profiles('{"profiles": {}}')
        assert len(result) == 0

    def test_parse_profile_without_images(self):
        """Test parsing profile without images key."""
        data = {"profiles": {"test": {"name": "Test"}}}
        result = parse_profiles(json.dumps(data))
        assert len(result) == 0

    def test_parse_file(self, tmp_path: Path, sample_profiles_json: str):
        """Test parsing from file."""
        file_path = tmp_path / "profiles.json"
        file_path.write_text(sample_profiles_json)

        result = parse_profiles_file(file_path)
        assert len(result) == 2

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON raises error."""
        with pytest.raises(json.JSONDecodeError):
            parse_profiles("not json")


class TestPackagesParser:
    """Tests for package index parsing."""

    def test_parse_packages(self, sample_packages_json: str):
        """Test parsing package index."""
        result = parse_packages(sample_packages_json)
        assert isinstance(result, PackageIndex)
        assert result.architecture == "x86_64"
        assert len(result.packages) == 3
        assert result.packages["busybox"] == "1.36.1"

    def test_get_version_map(self, sample_packages_json: str):
        """Test version map generation."""
        index = parse_packages(sample_packages_json)
        version_map = index.get_version_map()

        assert "base-files-1.0.0" in version_map
        assert version_map["base-files-1.0.0"] == ("base-files", "1.0.0")
        assert "busybox-1.36.1" in version_map

    def test_parse_empty_packages(self):
        """Test parsing empty package list."""
        result = parse_packages('{"architecture": "x86_64", "packages": {}}')
        assert result.architecture == "x86_64"
        assert len(result.packages) == 0

    def test_parse_file(self, tmp_path: Path, sample_packages_json: str):
        """Test parsing from file."""
        file_path = tmp_path / "index.json"
        file_path.write_text(sample_packages_json)

        result = parse_packages_file(file_path)
        assert result.architecture == "x86_64"
