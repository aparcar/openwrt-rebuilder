"""Tests for data models."""

import pytest

from rebuilder.models import Result, Results, Status, Suite


class TestStatus:
    """Tests for Status enum."""

    def test_status_values(self):
        """Test status enum has expected values."""
        assert Status.GOOD.value == "GOOD"
        assert Status.BAD.value == "BAD"
        assert Status.UNKNOWN.value == "UNKWN"

    def test_status_from_string(self):
        """Test creating status from string."""
        assert Status("GOOD") == Status.GOOD
        assert Status("BAD") == Status.BAD
        assert Status("UNKWN") == Status.UNKNOWN


class TestResult:
    """Tests for Result dataclass."""

    def test_result_creation(self, sample_result: Result):
        """Test creating a result."""
        assert sample_result.name == "base-files"
        assert sample_result.version == "1.0.0"
        assert sample_result.status == Status.GOOD

    def test_result_to_dict(self, sample_result: Result):
        """Test converting result to dictionary."""
        data = sample_result.to_dict()
        assert data["name"] == "base-files"
        assert data["status"] == "GOOD"  # String, not enum
        assert data["architecture"] == "x86_64"
        assert data["distro"] == "openwrt"

    def test_result_default_values(self):
        """Test result with default values."""
        result = Result(
            name="test",
            version="1.0",
            architecture="x86_64",
            suite="SNAPSHOT",
            distro="openwrt",
            status=Status.UNKNOWN,
        )
        assert result.artifact_url == ""
        assert result.build_id is None
        assert result.built_at is None
        assert result.has_diffoscope is False
        assert result.diffoscope_url is None


class TestResults:
    """Tests for Results container."""

    def test_empty_results(self):
        """Test empty results container."""
        results = Results()
        assert len(results.good) == 0
        assert len(results.bad) == 0
        assert results.total_count() == 0

    def test_add_result(self, sample_result: Result):
        """Test adding a result."""
        results = Results()
        results.add(sample_result)
        assert len(results.good) == 1
        assert results.good[0] == sample_result

    def test_add_bad_result(self):
        """Test adding a BAD result."""
        results = Results()
        result = Result(
            name="test",
            version="1.0",
            architecture="x86_64",
            suite="SNAPSHOT",
            distro="openwrt",
            status=Status.BAD,
            has_diffoscope=True,
            diffoscope_url="diffoscope/test.html",
        )
        results.add(result)
        assert len(results.bad) == 1
        assert len(results.good) == 0

    def test_total_count(self):
        """Test counting all results."""
        results = Results()
        for status in [Status.GOOD, Status.BAD, Status.UNKNOWN]:
            results.add(
                Result(
                    name="test",
                    version="1.0",
                    architecture="x86_64",
                    suite="SNAPSHOT",
                    distro="openwrt",
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
                architecture="x86_64",
                suite="SNAPSHOT",
                distro="openwrt",
                status=Status.GOOD,
            )
        )
        results.add(
            Result(
                name="b",
                version="1.0",
                architecture="x86_64",
                suite="SNAPSHOT",
                distro="openwrt",
                status=Status.GOOD,
            )
        )
        results.add(
            Result(
                name="c",
                version="1.0",
                architecture="x86_64",
                suite="SNAPSHOT",
                distro="openwrt",
                status=Status.BAD,
            )
        )

        stats = results.stats()
        assert stats["good"] == 2
        assert stats["bad"] == 1
        assert stats["unknown"] == 0


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
            architecture="x86/64",
            suite="SNAPSHOT",
            distro="openwrt",
            status=Status.GOOD,
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
        assert len(data["packages"]["GOOD"]) == 3
        assert len(data["packages"]["BAD"]) == 1

    def test_suite_from_dict(self, populated_suite: Suite):
        """Test creating suite from dictionary."""
        data = populated_suite.to_dict()
        new_suite = Suite.from_dict(data)

        assert new_suite.packages.total_count() == populated_suite.packages.total_count()
        assert new_suite.images.total_count() == populated_suite.images.total_count()
        assert len(new_suite.packages.good) == 3
        assert len(new_suite.packages.bad) == 1
