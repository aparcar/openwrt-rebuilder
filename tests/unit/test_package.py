"""Tests for the single-package rebuild helpers (name parse, build identity)."""

import pytest

from rebuilder.core.package import (
    PackageRebuildError,
    PackageSource,
    make_source,
    parse_package_name,
)


class TestParsePackageName:
    """Splitting <name>-<version>.apk into the package name."""

    def test_simple(self):
        assert parse_package_name("464xlat-13.apk") == "464xlat"

    def test_dashed_version(self):
        assert parse_package_name("adb-5.0.2~6fe92d1a-r4.apk") == "adb"

    def test_dashed_name(self):
        # Version begins at the first '-<digit>'.
        assert parse_package_name("ca-certificates-20240203.apk") == "ca-certificates"

    def test_non_apk(self):
        with pytest.raises(PackageRebuildError):
            parse_package_name("foo-1.0.ipk")

    def test_no_version(self):
        with pytest.raises(PackageRebuildError):
            parse_package_name("noversion.apk")


class TestMakeSource:
    """Building a PackageSource from the caller's package/target/release."""

    def test_snapshot(self):
        src = make_source("tmate-2.4.0-r3.apk", "x86/64", "SNAPSHOT")
        assert src == PackageSource(target="x86/64", release="SNAPSHOT", name="tmate")
        assert src.version_path == "snapshots"

    def test_release(self):
        src = make_source("foo-1.0.apk", "mediatek/filogic", "24.10.0")
        assert src.target == "mediatek/filogic"
        assert src.release == "24.10.0"
        assert src.version_path == "releases/24.10.0"

    def test_branch_release(self):
        src = make_source("bar-2.apk", "x86/64", "24.10-SNAPSHOT")
        assert src.version_path == "releases/24.10-SNAPSHOT"

    def test_missing_target(self):
        with pytest.raises(PackageRebuildError):
            make_source("foo-1.apk", "", "SNAPSHOT")

    def test_package_arch_is_not_a_target(self):
        # Callers must map the arch from the apk URL to a target themselves.
        with pytest.raises(PackageRebuildError):
            make_source("foo-1.apk", "x86_64", "SNAPSHOT")

    def test_missing_release(self):
        with pytest.raises(PackageRebuildError):
            make_source("foo-1.apk", "x86/64", "")
