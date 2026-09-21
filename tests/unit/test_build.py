"""Tests for quoting OpenWrt's build logs into the rebuilder output."""

import os
from pathlib import Path

from rebuilder.core import build
from rebuilder.core.build import failure_report


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
