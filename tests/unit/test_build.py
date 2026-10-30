"""Tests for quoting OpenWrt's build logs into the rebuilder output."""

import os
from pathlib import Path

import pytest

from rebuilder.config import Config
from rebuilder.core import build
from rebuilder.core.build import BuildError, OpenWrtBuilder, failure_report
from rebuilder.core.command import CommandError

FEEDS_BUILDINFO = """\
src-git packages https://git.openwrt.org/feed/packages.git^0123abc
src-git luci https://git.openwrt.org/project/luci.git^4567def
"""


class TestFeedsBuildinfo:
    """feeds.conf written from the published feeds.buildinfo."""

    @pytest.fixture(autouse=True)
    def _published(self, monkeypatch):
        monkeypatch.setattr(build, "download_text", lambda url: FEEDS_BUILDINFO)

    def test_upstream_feeds_used_as_published(self, config: Config):
        config.rebuild_dir.mkdir(parents=True)
        assert OpenWrtBuilder(config).setup_feeds_buildinfo() == FEEDS_BUILDINFO
        assert (config.rebuild_dir / "feeds.conf").read_text() == FEEDS_BUILDINFO

    def test_mirror_replaces_feed_urls(self, config: Config):
        config.rebuild_dir.mkdir(parents=True)
        config.source_mirror = "https://codeberg.org/openwrt/"
        feeds = OpenWrtBuilder(config).setup_feeds_buildinfo()
        assert "git.openwrt.org" not in feeds
        assert "https://codeberg.org/openwrt/packages.git^0123abc" in feeds
        assert "https://codeberg.org/openwrt/luci.git^4567def" in feeds


def _log(log_dir: Path, rel: str, text: str, mtime: int = 1000) -> None:
    path = log_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.utime(path, (mtime, mtime))


class TestFailureReport:
    """What a failed make adds to the (rebuilderd-captured) output."""

    def test_no_error_txt(self, tmp_path: Path):
        assert failure_report(tmp_path) == ""
        assert failure_report(tmp_path / "missing") == ""

    def test_lists_failures_and_quotes_the_log(self, tmp_path: Path):
        _log(
            tmp_path,
            "package/error.txt",
            "   ERROR: package/feeds/packages/foo failed to build.\n",
        )
        _log(tmp_path, "package/feeds/packages/foo/download.txt", "fetched\n", mtime=1)
        _log(
            tmp_path,
            "package/feeds/packages/foo/compile.txt",
            "".join(f"line {i}\n" for i in range(100)) + "foo.c:3: error: boom\n",
        )

        report = failure_report(tmp_path)

        assert "  ERROR: package/feeds/packages/foo failed to build." in report
        assert "--- tail of package/feeds/packages/foo/compile.txt ---" in report
        assert report.endswith("foo.c:3: error: boom")
        assert "line 40" not in report  # only the tail
        assert "fetched" not in report  # newest log only

    def test_host_and_variant_failures(self, tmp_path: Path):
        _log(
            tmp_path,
            "package/error.txt",
            "ERROR: package/libs/bar [host] failed to build.\n"
            "ERROR: package/network/baz failed to build (build variant: full).\n",
        )
        _log(tmp_path, "package/libs/bar/host-compile.txt", "bar broke\n")
        _log(tmp_path, "package/network/baz/full/compile.txt", "baz broke\n")

        report = failure_report(tmp_path)

        assert "bar broke" in report
        assert "baz broke" in report

    def test_caps_quoted_logs(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(build, "MAX_FAILED_LOGS", 1)
        _log(
            tmp_path,
            "package/error.txt",
            "ERROR: package/a failed to build.\nERROR: package/b failed to build.\n",
        )
        _log(tmp_path, "package/a/compile.txt", "a log\n")
        _log(tmp_path, "package/b/compile.txt", "b log\n")

        report = failure_report(tmp_path)

        assert "ERROR: package/b failed to build." in report  # still listed
        assert "b log" not in report
        assert "(logs of the other 1 failures not shown)" in report


class FakeRunner:
    """Records make invocations; fails the ones naming a target in ``failing``."""

    def __init__(self, failing: tuple[str, ...] = ()):
        self.failing = failing
        self.cmds: list[list[str]] = []

    def run(self, cmd, **kwargs):
        self.cmds.append(list(cmd))
        if any(target in cmd for target in self.failing):
            raise CommandError(cmd, 2)

    def targets(self) -> list[str]:
        """The first make target of every invocation, in order."""
        return [
            next(arg for arg in cmd[1:] if "=" not in arg and not arg.startswith("-"))
            for cmd in self.cmds
        ]


def _builder(config: Config, runner: FakeRunner) -> OpenWrtBuilder:
    builder = OpenWrtBuilder(config)
    builder.runner = runner  # type: ignore[assignment]
    return builder


class TestMake:
    """The make command line."""

    def test_ignores_failed_packages_of_any_selection(self, config: Config):
        runner = FakeRunner()
        _builder(config, runner).make("package/compile")
        assert "IGNORE_ERRORS=n m y" in runner.cmds[0]
        assert "-k" not in runner.cmds[0]

    def test_images_keep_going(self, config: Config):
        runner = FakeRunner()
        _builder(config, runner).build_images()
        assert runner.cmds == [[*runner.cmds[0][:-2], "-k", "target/install"]]


class TestFullBuild:
    """Which failures stop the build and which only lose their artifacts."""

    def test_all_steps_succeed(self, config: Config):
        assert _builder(config, FakeRunner()).full_build() == []

    @pytest.mark.parametrize("failing", ["tools/install", "toolchain/install", "target/compile"])
    def test_toolchain_and_kernel_are_fatal(self, config: Config, failing: str):
        runner = FakeRunner(failing=(failing,))
        with pytest.raises(BuildError):
            _builder(config, runner).full_build()
        assert "package/compile" not in runner.targets()

    def test_failed_package_install_still_attempts_images_and_metadata(self, config: Config):
        runner = FakeRunner(failing=("package/install",))

        failures = _builder(config, runner).full_build()

        assert [err.step for err in failures] == ["package/install"]
        targets = runner.targets()
        assert "package/index" not in targets  # the rest of that step is skipped
        assert "target/install" in targets
        assert "checksum" in targets

    def test_failed_images_still_generate_metadata(self, config: Config):
        runner = FakeRunner(failing=("target/install",))

        failures = _builder(config, runner).full_build()

        assert [err.step for err in failures] == ["target/install"]
        assert runner.targets()[-3:] == ["buildinfo", "json_overview_image_info", "checksum"]

    def test_skipped_packages_are_reported(self, config: Config, caplog):
        _log(
            config.results_dir / "logs",
            "package/error.txt",
            "ERROR: package/boot/uboot-fritz4040 failed to build (build variant: fritz7520).\n",
        )

        with caplog.at_level("WARNING"):
            assert _builder(config, FakeRunner()).full_build() == []

        assert "uboot-fritz4040 failed to build" in caplog.text
