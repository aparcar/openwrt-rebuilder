"""Tests for data models."""

import pytest

from rebuilder.models import Result, Results, Status, Suite


class TestStatus:
    """Tests for Status enum."""

    def test_status_values(self):
        """Test status enum has expected values."""
        assert Status.REPRODUCIBLE.value == "reproducible"
        assert Status.UNREPRODUCIBLE.value == "unreproducible"
        assert Status.NOTFOUND.value == "notfound"
        assert Status.PENDING.value == "pending"

    def test_status_from_string(self):
        """Test creating status from string."""
        assert Status("reproducible") == Status.REPRODUCIBLE
        assert Status("unreproducible") == Status.UNREPRODUCIBLE


class TestResult:
    """Tests for Result dataclass."""

    def test_result_creation(self, sample_result: Result):
        """Test creating a result."""
        assert sample_result.name == "base-files"
        assert sample_result.version == "1.0.0"
        assert sample_result.status == Status.REPRODUCIBLE

    def test_result_to_dict(self, sample_result: Result):
        """Test converting result to dictionary."""
        data = sample_result.to_dict()
        assert data["name"] == "base-files"
        assert data["status"] == "reproducible"  # String, not enum
        assert data["files"]["reproducible"] == ["packages/base/base-files-1.0.0.ipk"]

    def test_result_default_values(self):
        """Test result with default values."""
        result = Result(
            name="test",
            version="1.0",
            arch="x86_64",
            distribution="openwrt",
            status=Status.PENDING,
        )
        assert result.metadata == {}
        assert result.log is None
        assert result.epoch == 0
        assert result.diffoscope is None
        assert result.files == {}


class TestResults:
    """Tests for Results container."""

    def test_empty_results(self):
        """Test empty results container."""
        results = Results()
        assert len(results.reproducible) == 0
        assert len(results.unreproducible) == 0
        assert results.total_count() == 0

    def test_add_result(self, sample_result: Result):
        """Test adding a result."""
        results = Results()
        results.add(sample_result)
        assert len(results.reproducible) == 1
        assert results.reproducible[0] == sample_result

    def test_add_unreproducible_result(self):
        """Test adding an unreproducible result."""
        results = Results()
        result = Result(
            name="test",
            version="1.0",
            arch="x86_64",
            distribution="openwrt",
            status=Status.UNREPRODUCIBLE,
            diffoscope="test.html",
        )
        results.add(result)
        assert len(results.unreproducible) == 1
        assert len(results.reproducible) == 0

    def test_total_count(self):
        """Test counting all results."""
        results = Results()
        for status in [Status.REPRODUCIBLE, Status.UNREPRODUCIBLE, Status.NOTFOUND]:
            results.add(
                Result(
                    name="test",
                    version="1.0",
                    arch="x86_64",
                    distribution="openwrt",
                    status=status,
                )
            )
        assert results.total_count() == 3

    def test_stats(self):
        """Test statistics generation."""
        results = Results()
        results.add(
            Result(
                name="a",
                version="1.0",
                arch="x86_64",
                distribution="openwrt",
                status=Status.REPRODUCIBLE,
            )
        )
        results.add(
            Result(
                name="b",
                version="1.0",
                arch="x86_64",
                distribution="openwrt",
                status=Status.REPRODUCIBLE,
            )
        )
        results.add(
            Result(
                name="c",
                version="1.0",
                arch="x86_64",
                distribution="openwrt",
                status=Status.UNREPRODUCIBLE,
            )
        )

        stats = results.stats()
        assert stats["reproducible"] == 2
        assert stats["unreproducible"] == 1
        assert stats["notfound"] == 0
        assert stats["pending"] == 0


class TestSuite:
    """Tests for Suite container."""

    def test_empty_suite(self, suite: Suite):
        """Test empty suite."""
        assert suite.packages.total_count() == 0
        assert suite.images.total_count() == 0

    def test_add_package_result(self, suite: Suite, sample_result: Result):
        """Test adding a package result."""
        suite.add_result("packages", sample_result)
        assert suite.packages.total_count() == 1
        assert suite.images.total_count() == 0

    def test_add_image_result(self, suite: Suite):
        """Test adding an image result."""
        result = Result(
            name="openwrt-x86-64.img",
            version="SNAPSHOT",
            arch="x86/64",
            distribution="openwrt",
            status=Status.REPRODUCIBLE,
        )
        suite.add_result("images", result)
        assert suite.images.total_count() == 1
        assert suite.packages.total_count() == 0

    def test_add_invalid_category(self, suite: Suite, sample_result: Result):
        """Test adding to invalid category raises error."""
        with pytest.raises(ValueError, match="Invalid category"):
            suite.add_result("invalid", sample_result)

    def test_suite_to_dict(self, populated_suite: Suite):
        """Test converting suite to dictionary."""
        data = populated_suite.to_dict()
        assert "packages" in data
        assert "images" in data
        assert len(data["packages"]["reproducible"]) == 3
        assert len(data["packages"]["unreproducible"]) == 1

    def test_suite_from_dict(self, populated_suite: Suite):
        """Test creating suite from dictionary."""
        data = populated_suite.to_dict()
        new_suite = Suite.from_dict(data)

        assert new_suite.packages.total_count() == populated_suite.packages.total_count()
        assert new_suite.images.total_count() == populated_suite.images.total_count()
        assert len(new_suite.packages.reproducible) == 3
        assert len(new_suite.packages.unreproducible) == 1
