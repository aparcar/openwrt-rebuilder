"""Git operations for managing the OpenWrt source repository."""

import logging
from pathlib import Path

from rebuilder.config import Config
from rebuilder.core.command import CommandError, CommandRunner

logger = logging.getLogger(__name__)


class GitError(Exception):
    """Raised when a git operation fails."""

    def __init__(self, operation: str, message: str):
        self.operation = operation
        super().__init__(f"Git {operation} failed: {message}")


class GitRepository:
    """Manages git operations for the OpenWrt source repository."""

    def __init__(self, config: Config):
        """Initialize git repository manager.

        Args:
            config: Rebuild configuration.
        """
        self.config = config
        self.path = config.rebuild_dir
        self.runner = CommandRunner(cwd=self.path)

    def _git(
        self,
        *args: str,
        capture: bool = False,
        ignore_errors: bool = False,
    ) -> str:
        """Run a git command.

        Args:
            *args: Git command arguments.
            capture: Whether to capture output.
            ignore_errors: Whether to ignore errors.

        Returns:
            Command output if capture=True, empty string otherwise.
        """
        cmd = ["git", *args]
        result = self.runner.run(cmd, capture=capture, ignore_errors=ignore_errors)
        return result.stdout.strip() if capture else ""

    def clone(self) -> None:
        """Clone the OpenWrt repository if it doesn't exist.

        If the repository already exists, fetch and reset to the target branch.
        Ensures full history is available for SOURCE_DATE_EPOCH calculation.
        """
        if not self.path.is_dir():
            logger.info(f"Cloning {self.config.openwrt_git} to {self.path}")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            runner = CommandRunner(cwd=self.path.parent)
            runner.run(["git", "clone", self.config.openwrt_git, str(self.path)], capture=True)
        else:
            logger.info("Updating existing repository")
            # Unshallow if this is a shallow clone (needed for SOURCE_DATE_EPOCH)
            self._git("fetch", "--unshallow", capture=True, ignore_errors=True)
            self._git("fetch", "--all", capture=True)
            self._git("reset", "--hard", f"origin/{self.config.branch}", capture=True)

    def checkout(self, commit: str) -> None:
        """Checkout a specific commit.

        Args:
            commit: Commit hash or reference to checkout.
        """
        logger.info(f"Checking out {self.config.branch}")
        self._git("checkout", self.config.branch, capture=True)
        self._git("reset", "--hard", commit, capture=True)

        # For release versions, create a version tag branch
        if self.config.version != "SNAPSHOT":
            tag = f"v{self.config.version}"
            # Delete existing branch if it exists
            self._git("branch", "-f", "-D", tag, capture=True, ignore_errors=True)
            # Create and checkout the tag branch
            self._git("checkout", tag, "-f", "-b", tag, capture=True)

    def get_version_string(self) -> str:
        """Get the version string from getver.sh.

        Returns:
            Version string from the repository.
        """
        result = self.runner.run(
            ["bash", "./scripts/getver.sh"],
            capture=True,
        )
        return result.stdout.strip()

    def get_head_commit(self) -> str:
        """Get the current HEAD commit hash.

        Returns:
            Full commit hash of HEAD.
        """
        return self._git("rev-parse", "HEAD", capture=True)

    def get_short_commit(self) -> str:
        """Get the short form of the current HEAD commit.

        Returns:
            Short commit hash of HEAD.
        """
        return self._git("rev-parse", "--short", "HEAD", capture=True)

    def is_clean(self) -> bool:
        """Check if the working directory is clean.

        Returns:
            True if there are no uncommitted changes.
        """
        status = self._git("status", "--porcelain", capture=True)
        return len(status) == 0

    def apply_patch(self, patch_path: Path) -> bool:
        """Apply a patch file to the repository.

        Args:
            patch_path: Path to the patch file.

        Returns:
            True if the patch was applied successfully.
        """
        logger.info(f"Applying patch: {patch_path.name}")
        try:
            self._git("apply", str(patch_path), capture=True)
            return True
        except CommandError as e:
            logger.error(f"Failed to apply {patch_path.name}: {e}")
            return False

    def apply_patches(self, patches_dir: Path) -> int:
        """Apply all patches from a directory.

        Args:
            patches_dir: Directory containing .patch files.

        Returns:
            Number of patches successfully applied.
        """
        if not patches_dir.exists():
            logger.info(f"No patches directory found: {patches_dir}")
            return 0

        patch_files = sorted(patches_dir.glob("*.patch"))
        if not patch_files:
            logger.info(f"No patches found in {patches_dir}")
            return 0

        logger.info(f"Applying {len(patch_files)} patches")
        applied = sum(1 for p in patch_files if self.apply_patch(p))
        return applied


def clone_repository(config: Config) -> GitRepository:
    """Clone or update the OpenWrt repository.

    Args:
        config: Rebuild configuration.

    Returns:
        GitRepository instance for the cloned repository.
    """
    repo = GitRepository(config)
    repo.clone()
    return repo
