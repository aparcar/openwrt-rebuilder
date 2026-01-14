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

    def test_compare_file_reproducible(self, comparator: Comparator):
        """Test comparing identical files."""
        status = comparator.compare_file(
            "test.ipk",
            "abc123",
            {"test.ipk": "abc123"},
        )
        assert status == Status.REPRODUCIBLE

    def test_compare_file_unreproducible(self, comparator: Comparator):
        """Test comparing different files."""
        status = comparator.compare_file(
            "test.ipk",
            "abc123",
            {"test.ipk": "different"},
        )
        assert status == Status.UNREPRODUCIBLE

    def test_compare_file_not_found(self, comparator: Comparator):
        """Test comparing missing file."""
        status = comparator.compare_file(
            "missing.ipk",
            "abc123",
            {"other.ipk": "abc123"},
        )
        assert status == Status.NOTFOUND


class TestCompareProfiles:
    """Tests for profile comparison."""

    def test_compare_profiles_reproducible(
        self, config: Config, suite: Suite, tmp_path: Path
    ):
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

        assert len(suite.images.reproducible) == 1
        assert suite.images.reproducible[0].status == Status.REPRODUCIBLE

    def test_compare_profiles_unreproducible(
        self, config: Config, suite: Suite, tmp_path: Path
    ):
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

        assert len(suite.images.unreproducible) == 1
        assert suite.images.unreproducible[0].diffoscope == "test.img.html"

    def test_compare_profiles_not_found(
        self, config: Config, suite: Suite, tmp_path: Path
    ):
        """Test comparing missing profile."""
        rebuild_profiles = {"profiles": {}}
        profiles_path = tmp_path / "profiles.json"
        profiles_path.write_text(json.dumps(rebuild_profiles))

        origin = {"missing.img": "abc123"}

        comparator = Comparator(config, suite)
        comparator.compare_profiles(origin, profiles_path)

        assert len(suite.images.notfound) == 1


class TestComparePackages:
    """Tests for package comparison."""

    def test_compare_packages_reproducible(
        self, config: Config, suite: Suite, tmp_path: Path
    ):
        """Test comparing reproducible packages."""
        # Create package index
        index = {"architecture": "x86_64", "packages": {"foo": "1.0"}}
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index))

        origin = {"foo-1.0.ipk": "abc123"}
        rebuild = {"foo-1.0.ipk": "abc123"}

        comparator = Comparator(config, suite)
        comparator.compare_packages(origin, rebuild, index_path, "packages/base")

        assert len(suite.packages.reproducible) == 1
        assert suite.packages.reproducible[0].name == "foo"

    def test_compare_packages_unreproducible(
        self, config: Config, suite: Suite, tmp_path: Path
    ):
        """Test comparing unreproducible packages."""
        index = {"architecture": "x86_64", "packages": {"foo": "1.0"}}
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index))

        origin = {"foo-1.0.ipk": "abc123"}
        rebuild = {"foo-1.0.ipk": "different"}

        comparator = Comparator(config, suite)
        comparator.compare_packages(origin, rebuild, index_path, "packages/base")

        assert len(suite.packages.unreproducible) == 1
        assert suite.packages.unreproducible[0].diffoscope == "foo-1.0.ipk.html"

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

    def test_compare_packages_handles_apk(
        self, config: Config, suite: Suite, tmp_path: Path
    ):
        """Test that .apk files are handled."""
        index = {"architecture": "x86_64", "packages": {"foo": "1.0"}}
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index))

        origin = {"foo-1.0.apk": "abc123"}
        rebuild = {"foo-1.0.apk": "abc123"}

        comparator = Comparator(config, suite)
        comparator.compare_packages(origin, rebuild, index_path, "packages/base")

        assert len(suite.packages.reproducible) == 1
