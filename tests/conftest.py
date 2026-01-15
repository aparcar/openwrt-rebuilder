"""Pytest fixtures and configuration."""

import json
from pathlib import Path

import pytest

from rebuilder.config import Config
from rebuilder.models import Result, Status, Suite


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_sha256sums() -> str:
    """Sample sha256sums file content."""
    # SHA256 hashes are 64 hex chars
    hash1 = "abc123def456789012345678901234567890123456789012345678901234abcd"
    hash2 = "def456abc789012345678901234567890123456789012345678901234567ef01"
    hash3 = "7890123456789012345678901234567890123456789012345678901234567890"
    return f"""{hash1} *packages/base/foo-1.0.0.ipk
{hash2} *packages/base/bar-2.1.0.ipk
{hash3} *targets/x86/64/openwrt-x86-64-generic-squashfs-combined.img.gz
"""


@pytest.fixture
def sample_profiles_json() -> str:
    """Sample profiles.json content."""
    return json.dumps(
        {
            "profiles": {
                "generic": {
                    "images": [
                        {
                            "name": "openwrt-x86-64-generic-squashfs-combined.img.gz",
                            "sha256": "abc123def456789012345678901234567890123456789012345678901234abcd",
                        },
                        {
                            "name": "openwrt-x86-64-generic-ext4-combined.img.gz",
                            "sha256": "def456abc789012345678901234567890123456789012345678901234567ef01",
                        },
                    ]
                }
            }
        }
    )


@pytest.fixture
def sample_packages_json() -> str:
    """Sample package index.json content."""
    return json.dumps(
        {
            "architecture": "x86_64",
            "packages": {"base-files": "1.0.0", "busybox": "1.36.1", "dnsmasq": "2.90"},
        }
    )


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
        use_diffoscope=False,
        jobs=2,
    )


@pytest.fixture
def suite() -> Suite:
    """Create an empty test suite."""
    return Suite()


@pytest.fixture
def sample_result() -> Result:
    """Create a sample result for testing."""
    return Result(
        name="base-files",
        version="1.0.0",
        architecture="x86_64",
        suite="SNAPSHOT",
        distro="openwrt",
        status=Status.GOOD,
    )


@pytest.fixture
def populated_suite() -> Suite:
    """Create a suite with sample results."""
    suite = Suite()

    # Add some GOOD packages
    for i in range(3):
        suite.add_result(
            "packages",
            Result(
                name=f"pkg-{i}",
                version="1.0",
                architecture="x86_64",
                suite="SNAPSHOT",
                distro="openwrt",
                status=Status.GOOD,
            ),
        )

    # Add a BAD package
    suite.add_result(
        "packages",
        Result(
            name="unrep-pkg",
            version="2.0",
            architecture="x86_64",
            suite="SNAPSHOT",
            distro="openwrt",
            status=Status.BAD,
            has_diffoscope=True,
            diffoscope_url="diffoscope/unrep-pkg-2.0.ipk.html",
        ),
    )

    # Add an UNKNOWN package
    suite.add_result(
        "packages",
        Result(
            name="missing-pkg",
            version="1.0",
            architecture="x86_64",
            suite="SNAPSHOT",
            distro="openwrt",
            status=Status.UNKNOWN,
        ),
    )

    # Add GOOD images
    suite.add_result(
        "images",
        Result(
            name="openwrt-x86-64-generic.img",
            version="SNAPSHOT",
            architecture="x86/64",
            suite="SNAPSHOT",
            distro="openwrt",
            status=Status.GOOD,
        ),
    )

    return suite
