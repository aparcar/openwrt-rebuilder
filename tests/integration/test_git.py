"""Integration tests for git operations."""

from pathlib import Path

import pytest

from rebuilder.config import Config
from rebuilder.core.git import GitRepository


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository for testing."""
    from rebuilder.core.command import run_command

    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repository
    run_command(["git", "init"], cwd=repo_path)
    run_command(["git", "config", "user.email", "test@test.com"], cwd=repo_path)
    run_command(["git", "config", "user.name", "Test User"], cwd=repo_path)

    # Create initial commit
    (repo_path / "README.md").write_text("# Test Repository\n")
    run_command(["git", "add", "README.md"], cwd=repo_path)
    run_command(["git", "commit", "-m", "Initial commit"], cwd=repo_path)

    # Create a branch
    run_command(["git", "checkout", "-b", "master"], cwd=repo_path, ignore_errors=True)

    return repo_path


@pytest.fixture
def config_with_local_repo(tmp_path: Path, git_repo: Path) -> Config:
    """Create a config pointing to a local git repository."""
    return Config(
        target="x86/64",
        version="SNAPSHOT",
        rebuild_dir=tmp_path / "build",
        dl_dir=tmp_path / "dl",
        results_dir=tmp_path / "results",
        openwrt_git=str(git_repo),
    )


class TestGitRepository:
    """Tests for GitRepository class."""

    def test_clone_new_repository(self, config_with_local_repo: Config):
        """Test cloning a new repository."""
        repo = GitRepository(config_with_local_repo)
        repo.clone()

        # Verify the repository was cloned
        assert config_with_local_repo.rebuild_dir.exists()
        assert (config_with_local_repo.rebuild_dir / ".git").exists()
        assert (config_with_local_repo.rebuild_dir / "README.md").exists()

    def test_clone_existing_repository(self, config_with_local_repo: Config):
        """Test updating an existing repository."""
        repo = GitRepository(config_with_local_repo)

        # Clone first time
        repo.clone()

        # Clone again (should update)
        repo.clone()

        # Verify still works
        assert (config_with_local_repo.rebuild_dir / ".git").exists()

    def test_get_head_commit(self, config_with_local_repo: Config):
        """Test getting HEAD commit hash."""
        repo = GitRepository(config_with_local_repo)
        repo.clone()

        commit = repo.get_head_commit()
        assert len(commit) == 40  # Full SHA-1 hash
        assert all(c in "0123456789abcdef" for c in commit)

    def test_get_short_commit(self, config_with_local_repo: Config):
        """Test getting short commit hash."""
        repo = GitRepository(config_with_local_repo)
        repo.clone()

        short_commit = repo.get_short_commit()
        assert len(short_commit) >= 7
        assert len(short_commit) <= 40

    def test_is_clean(self, config_with_local_repo: Config):
        """Test checking if repository is clean."""
        repo = GitRepository(config_with_local_repo)
        repo.clone()

        # Should be clean after fresh clone
        assert repo.is_clean()

        # Make a change
        (config_with_local_repo.rebuild_dir / "new_file.txt").write_text("test")

        # Should not be clean now
        assert not repo.is_clean()


class TestGitPatches:
    """Tests for patch application."""

    def test_apply_patch(self, config_with_local_repo: Config, tmp_path: Path):
        """Test applying a patch."""
        repo = GitRepository(config_with_local_repo)
        repo.clone()

        # Create a patch file
        patch_content = """--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # Test Repository
+Added line by patch
"""
        patch_file = tmp_path / "test.patch"
        patch_file.write_text(patch_content)

        # Apply the patch
        result = repo.apply_patch(patch_file)
        assert result is True

        # Verify the patch was applied
        readme_content = (config_with_local_repo.rebuild_dir / "README.md").read_text()
        assert "Added line by patch" in readme_content

    def test_apply_patches_directory(self, config_with_local_repo: Config, tmp_path: Path):
        """Test applying patches from a directory."""
        repo = GitRepository(config_with_local_repo)
        repo.clone()

        # Create patches directory with multiple patches
        patches_dir = tmp_path / "patches"
        patches_dir.mkdir()

        patch1 = """--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # Test Repository
+First patch
"""
        (patches_dir / "001-first.patch").write_text(patch1)

        patch2 = """--- a/README.md
+++ b/README.md
@@ -1,2 +1,3 @@
 # Test Repository
 First patch
+Second patch
"""
        (patches_dir / "002-second.patch").write_text(patch2)

        # Apply all patches
        applied = repo.apply_patches(patches_dir)
        assert applied == 2

        # Verify both patches were applied
        readme_content = (config_with_local_repo.rebuild_dir / "README.md").read_text()
        assert "First patch" in readme_content
        assert "Second patch" in readme_content

    def test_apply_patches_nonexistent_directory(
        self, config_with_local_repo: Config, tmp_path: Path
    ):
        """Test applying patches from nonexistent directory."""
        repo = GitRepository(config_with_local_repo)
        repo.clone()

        patches_dir = tmp_path / "nonexistent"
        applied = repo.apply_patches(patches_dir)
        assert applied == 0

    def test_apply_patches_empty_directory(self, config_with_local_repo: Config, tmp_path: Path):
        """Test applying patches from empty directory."""
        repo = GitRepository(config_with_local_repo)
        repo.clone()

        patches_dir = tmp_path / "empty_patches"
        patches_dir.mkdir()

        applied = repo.apply_patches(patches_dir)
        assert applied == 0
