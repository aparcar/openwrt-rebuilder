"""Tests for history functionality in combine.py."""

from pathlib import Path

import pytest

from rebuilder.reporting.combine import (
    MAX_HISTORY_ENTRIES,
    VersionHistory,
    cleanup_old_artifacts,
    get_base_version,
    get_version_slug,
    load_history,
    save_history,
    update_history,
)
from rebuilder.reporting.html import BuildInfo


class TestGetVersionSlug:
    """Tests for get_version_slug function."""

    def test_release_version(self):
        """Test slug for release version."""
        assert get_version_slug("25.12.1") == "25_12_1"

    def test_snapshot_version(self):
        """Test slug for SNAPSHOT version."""
        assert get_version_slug("SNAPSHOT") == "SNAPSHOT"

    def test_snapshot_with_version_code(self):
        """Test slug for SNAPSHOT with version code."""
        assert get_version_slug("SNAPSHOT/r28532-abc123") == "SNAPSHOT_r28532-abc123"

    def test_branch_snapshot(self):
        """Test slug for branch SNAPSHOT."""
        assert get_version_slug("25.12-SNAPSHOT") == "25_12-SNAPSHOT"


class TestGetBaseVersion:
    """Tests for get_base_version function."""

    def test_release_version(self):
        """Test base version for release."""
        base, code = get_base_version("25.12.1")
        assert base == "25.12.1"
        assert code is None

    def test_snapshot_with_code(self):
        """Test base version for SNAPSHOT with version code."""
        base, code = get_base_version("SNAPSHOT/r28532-abc123")
        assert base == "SNAPSHOT"
        assert code == "r28532-abc123"

    def test_snapshot_without_code(self):
        """Test base version for SNAPSHOT without version code."""
        base, code = get_base_version("SNAPSHOT")
        assert base == "SNAPSHOT"
        assert code is None

    def test_branch_snapshot_with_code(self):
        """Test base version for branch SNAPSHOT with code."""
        base, code = get_base_version("25.12-SNAPSHOT/r12345-def456")
        assert base == "25.12-SNAPSHOT"
        assert code == "r12345-def456"


class TestLoadSaveHistory:
    """Tests for load_history and save_history functions."""

    def test_load_nonexistent_history(self, tmp_path: Path):
        """Test loading history that doesn't exist."""
        history = load_history(tmp_path, "SNAPSHOT")

        assert history["version"] == "SNAPSHOT"
        assert history["entries"] == []

    def test_save_and_load_history(self, tmp_path: Path):
        """Test saving and loading history."""
        history: VersionHistory = {
            "version": "25.12.1",
            "entries": [
                {
                    "timestamp": "2025-01-16T12:00:00+00:00",
                    "version_code": None,
                    "run_id": "12345",
                    "commit": "abc123",
                    "stats": {"good": 100, "bad": 10, "unknown": 5},
                    "targets": {
                        "x86/64": {"good": 50, "bad": 5, "unknown": 2},
                    },
                }
            ],
        }

        save_history(tmp_path, "25.12.1", history)

        # Check file was created
        history_path = tmp_path / "25_12_1" / "history.json"
        assert history_path.exists()

        # Load and verify
        loaded = load_history(tmp_path, "25.12.1")
        assert loaded["version"] == "25.12.1"
        assert len(loaded["entries"]) == 1
        assert loaded["entries"][0]["stats"]["good"] == 100

    def test_load_corrupted_history(self, tmp_path: Path):
        """Test loading corrupted history file."""
        version_dir = tmp_path / "SNAPSHOT"
        version_dir.mkdir(parents=True)
        history_path = version_dir / "history.json"
        history_path.write_text("invalid json {")

        history = load_history(tmp_path, "SNAPSHOT")

        # Should return empty history on error
        assert history["version"] == "SNAPSHOT"
        assert history["entries"] == []


class TestUpdateHistory:
    """Tests for update_history function."""

    @pytest.fixture
    def build_info(self) -> BuildInfo:
        """Create test build info."""
        return BuildInfo(
            time="2025-01-16 12:00:00 UTC",
            commit="abc123",
            branch="main",
            run_id="12345",
        )

    def test_add_first_entry(self, build_info: BuildInfo):
        """Test adding first entry to empty history."""
        history: VersionHistory = {"version": "SNAPSHOT", "entries": []}
        stats = {"good": 100, "bad": 10, "unknown": 5}
        targets = {"x86/64": {"good": 50, "bad": 5, "unknown": 2}}

        result = update_history(
            history,
            stats,
            targets,
            "r28532-abc123",
            build_info,
            "2025-01-16T12:00:00+00:00",
        )

        assert len(result["entries"]) == 1
        assert result["entries"][0]["version_code"] == "r28532-abc123"
        assert result["entries"][0]["stats"]["good"] == 100
        assert result["entries"][0]["run_id"] == "12345"

    def test_add_new_entry_to_existing(self, build_info: BuildInfo):
        """Test adding new entry to existing history."""
        history: VersionHistory = {
            "version": "SNAPSHOT",
            "entries": [
                {
                    "timestamp": "2025-01-15T12:00:00+00:00",
                    "version_code": "r28531-def456",
                    "run_id": "12344",
                    "commit": "def456",
                    "stats": {"good": 90, "bad": 15, "unknown": 10},
                    "targets": {},
                }
            ],
        }
        stats = {"good": 100, "bad": 10, "unknown": 5}
        targets = {"x86/64": {"good": 50, "bad": 5, "unknown": 2}}

        result = update_history(
            history,
            stats,
            targets,
            "r28532-abc123",
            build_info,
            "2025-01-16T12:00:00+00:00",
        )

        # New entry should be first (newest)
        assert len(result["entries"]) == 2
        assert result["entries"][0]["version_code"] == "r28532-abc123"
        assert result["entries"][1]["version_code"] == "r28531-def456"

    def test_update_existing_version_code(self, build_info: BuildInfo):
        """Test updating entry with same version code."""
        history: VersionHistory = {
            "version": "SNAPSHOT",
            "entries": [
                {
                    "timestamp": "2025-01-15T12:00:00+00:00",
                    "version_code": "r28532-abc123",
                    "run_id": "12344",
                    "commit": "old",
                    "stats": {"good": 90, "bad": 15, "unknown": 10},
                    "targets": {},
                }
            ],
        }
        stats = {"good": 100, "bad": 10, "unknown": 5}
        targets = {"x86/64": {"good": 50, "bad": 5, "unknown": 2}}

        result = update_history(
            history,
            stats,
            targets,
            "r28532-abc123",  # Same version code
            build_info,
            "2025-01-16T12:00:00+00:00",
        )

        # Should update existing entry, not add new one
        assert len(result["entries"]) == 1
        assert result["entries"][0]["stats"]["good"] == 100
        assert result["entries"][0]["commit"] == "abc123"

    def test_cap_at_max_entries(self, build_info: BuildInfo):
        """Test that history is capped at MAX_HISTORY_ENTRIES."""
        # Create history with MAX_HISTORY_ENTRIES entries
        history: VersionHistory = {
            "version": "SNAPSHOT",
            "entries": [
                {
                    "timestamp": f"2025-01-{i:02d}T12:00:00+00:00",
                    "version_code": f"r{28500 + i}-abc{i:03d}",
                    "run_id": str(12300 + i),
                    "commit": f"commit{i}",
                    "stats": {"good": 90, "bad": 10, "unknown": 5},
                    "targets": {},
                }
                for i in range(MAX_HISTORY_ENTRIES)
            ],
        }

        stats = {"good": 100, "bad": 0, "unknown": 0}
        targets = {}

        result = update_history(
            history,
            stats,
            targets,
            "r99999-new",
            build_info,
            "2025-02-01T12:00:00+00:00",
        )

        # Should still be capped at MAX_HISTORY_ENTRIES
        assert len(result["entries"]) == MAX_HISTORY_ENTRIES
        # New entry should be first
        assert result["entries"][0]["version_code"] == "r99999-new"


class TestCleanupOldArtifacts:
    """Tests for cleanup_old_artifacts function."""

    def test_cleanup_diffoscope(self, tmp_path: Path):
        """Test cleaning up diffoscope directory."""
        diffoscope_dir = tmp_path / "diffoscope"
        diffoscope_dir.mkdir()
        (diffoscope_dir / "old-file.html").write_text("old report")
        (diffoscope_dir / "another.html").write_text("another report")

        removed = cleanup_old_artifacts(tmp_path, "SNAPSHOT", "r28532-abc123")

        assert removed == 2
        # Files should be removed
        assert not (diffoscope_dir / "old-file.html").exists()
        assert not (diffoscope_dir / "another.html").exists()

    def test_cleanup_artifacts(self, tmp_path: Path):
        """Test cleaning up artifacts directory."""
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()
        pkg_dir = artifacts_dir / "packages" / "pkg1"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pkg1.ipk").write_text("binary")
        (pkg_dir / "pkg1.ipk.orig").write_text("original")

        removed = cleanup_old_artifacts(tmp_path, "SNAPSHOT", "r28532-abc123")

        assert removed == 1  # One top-level dir under artifacts
        assert not (artifacts_dir / "packages").exists()

    def test_cleanup_empty_dirs(self, tmp_path: Path):
        """Test cleanup when directories don't exist."""
        removed = cleanup_old_artifacts(tmp_path, "SNAPSHOT", "r28532-abc123")

        assert removed == 0

    def test_cleanup_preserves_output_dir(self, tmp_path: Path):
        """Test that output_dir itself is preserved."""
        diffoscope_dir = tmp_path / "diffoscope"
        diffoscope_dir.mkdir()
        (diffoscope_dir / "file.html").write_text("report")

        cleanup_old_artifacts(tmp_path, "SNAPSHOT", "r28532-abc123")

        # Directories should still exist (just empty)
        assert tmp_path.exists()
