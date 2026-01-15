"""Tests for comparison logic."""

import json
from pathlib import Path

import pytest

from rebuilder.config import Config
from rebuilder.core.compare import Comparator
from rebuilder.models import Status, Suite


@pytest.fixture
def comparator(config: Config, suite: Suite) -> Comparator:
    """Create a comparator for testing."""
    return Comparator(config, suite)


class TestComparator:
    """Tests for Comparator class."""

    def test_compare_file_good(self, comparator: Comparator):
        """Test comparing identical files."""
        status = comparator.compare_file(
            "test.ipk",
            "abc123",
            {"test.ipk": "abc123"},
        )
        assert status == Status.GOOD

    def test_compare_file_bad(self, comparator: Comparator):
        """Test comparing different files."""
        status = comparator.compare_file(
            "test.ipk",
            "abc123",
            {"test.ipk": "different"},
        )
        assert status == Status.BAD

    def test_compare_file_unknown(self, comparator: Comparator):
        """Test comparing missing file."""
        status = comparator.compare_file(
            "missing.ipk",
            "abc123",
            {"other.ipk": "abc123"},
        )
        assert status == Status.UNKNOWN


class TestCompareProfiles:
    """Tests for profile comparison."""

    def test_compare_profiles_good(self, config: Config, suite: Suite, tmp_path: Path):
        """Test comparing reproducible profiles."""
        # Create rebuild profiles
        rebuild_profiles = {
            "profiles": {
                "generic": {
                    "images": [
                        {"name": "test.img", "sha256": "abc123"},
                    ]
                }
            }
        }
        profiles_path = tmp_path / "profiles.json"
        profiles_path.write_text(json.dumps(rebuild_profiles))

        # Origin profiles with same checksum
        origin = {"test.img": "abc123"}

        comparator = Comparator(config, suite)
        comparator.compare_profiles(origin, profiles_path)

        assert len(suite.images.good) == 1
        assert suite.images.good[0].status == Status.GOOD

    def test_compare_profiles_bad(self, config: Config, suite: Suite, tmp_path: Path):
        """Test comparing unreproducible profiles."""
        rebuild_profiles = {
            "profiles": {
                "generic": {
                    "images": [
                        {"name": "test.img", "sha256": "different"},
                    ]
                }
            }
        }
        profiles_path = tmp_path / "profiles.json"
        profiles_path.write_text(json.dumps(rebuild_profiles))

        origin = {"test.img": "abc123"}

        comparator = Comparator(config, suite)
        comparator.compare_profiles(origin, profiles_path)

        assert len(suite.images.bad) == 1
        assert suite.images.bad[0].has_diffoscope is True
        assert suite.images.bad[0].diffoscope_url == "diffoscope/test.img.html"

    def test_compare_profiles_unknown(self, config: Config, suite: Suite, tmp_path: Path):
        """Test comparing missing profile."""
        rebuild_profiles = {"profiles": {}}
        profiles_path = tmp_path / "profiles.json"
        profiles_path.write_text(json.dumps(rebuild_profiles))

        origin = {"missing.img": "abc123"}

        comparator = Comparator(config, suite)
        comparator.compare_profiles(origin, profiles_path)

        assert len(suite.images.unknown) == 1


class TestComparePackages:
    """Tests for package comparison."""

    def test_compare_packages_good(self, config: Config, suite: Suite, tmp_path: Path):
        """Test comparing reproducible packages."""
        # Create package index
        index = {"architecture": "x86_64", "packages": {"foo": "1.0"}}
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index))

        origin = {"foo-1.0.ipk": "abc123"}
        rebuild = {"foo-1.0.ipk": "abc123"}

        comparator = Comparator(config, suite)
        comparator.compare_packages(origin, rebuild, index_path, "packages/base")

        assert len(suite.packages.good) == 1
        assert suite.packages.good[0].name == "foo"

    def test_compare_packages_bad(self, config: Config, suite: Suite, tmp_path: Path):
        """Test comparing unreproducible packages."""
        index = {"architecture": "x86_64", "packages": {"foo": "1.0"}}
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index))

        origin = {"foo-1.0.ipk": "abc123"}
        rebuild = {"foo-1.0.ipk": "different"}

        comparator = Comparator(config, suite)
        comparator.compare_packages(origin, rebuild, index_path, "packages/base")

        assert len(suite.packages.bad) == 1
        assert suite.packages.bad[0].has_diffoscope is True
        assert suite.packages.bad[0].diffoscope_url == "diffoscope/foo-1.0.ipk.html"

    def test_compare_packages_ignores_non_packages(
        self, config: Config, suite: Suite, tmp_path: Path
    ):
        """Test that non-package files are ignored."""
        index = {"architecture": "x86_64", "packages": {}}
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index))

        rebuild = {"readme.txt": "abc123", "checksums": "def456"}

        comparator = Comparator(config, suite)
        comparator.compare_packages({}, rebuild, index_path, "packages/base")

        assert suite.packages.total_count() == 0

    def test_compare_packages_handles_apk(self, config: Config, suite: Suite, tmp_path: Path):
        """Test that .apk files are handled."""
        index = {"architecture": "x86_64", "packages": {"foo": "1.0"}}
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index))

        origin = {"foo-1.0.apk": "abc123"}
        rebuild = {"foo-1.0.apk": "abc123"}

        comparator = Comparator(config, suite)
        comparator.compare_packages(origin, rebuild, index_path, "packages/base")

        assert len(suite.packages.good) == 1
