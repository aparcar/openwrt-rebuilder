"""Build operations for OpenWrt compilation."""

import logging
import re
from os import symlink

from rebuilder.config import Config
from rebuilder.core.command import CommandRunner
from rebuilder.core.download import download_text

logger = logging.getLogger(__name__)


class BuildError(Exception):
    """Raised when a build operation fails."""

    def __init__(self, step: str, message: str):
        self.step = step
        super().__init__(f"Build step '{step}' failed: {message}")


class OpenWrtBuilder:
    """Manages OpenWrt build operations."""

    def __init__(self, config: Config):
        """Initialize builder.

        Args:
            config: Rebuild configuration.
        """
        self.config = config
        self.runner = CommandRunner(cwd=config.rebuild_dir)
        self._commit: str | None = None
        self._commit_string: str | None = None
        self._kernel_version: str | None = None

    @property
    def commit(self) -> str:
        """Get the commit hash being built."""
        if self._commit is None:
            raise ValueError("Commit not set - call setup_version_buildinfo first")
        return self._commit

    @property
    def commit_string(self) -> str:
        """Get the full version string."""
        if self._commit_string is None:
            raise ValueError("Commit string not set - call setup_version_buildinfo first")
        return self._commit_string

    @property
    def kernel_version(self) -> str:
        """Get the kernel version string."""
        if self._kernel_version is None:
            raise ValueError("Kernel version not set - call setup_kernel_magic first")
        return self._kernel_version

    def make(self, *targets: str, jobs: int | None = None, verbose: bool = False) -> None:
        """Run make with the specified targets.

        Args:
            *targets: Make targets to build.
            jobs: Number of parallel jobs (default: from config).
            verbose: If True, show make output. Otherwise suppress it.
        """
        j = jobs if jobs is not None else self.config.jobs
        cmd = [
            "make",
            "IGNORE_ERRORS='n m'",
            "BUILD_LOG=1",
            f"BUILD_LOG_DIR={self.config.results_dir}/logs",
            f"-j{j}",
            *targets,
        ]
        # Capture output to suppress it (logs are written to BUILD_LOG_DIR)
        self.runner.run(cmd, capture=not verbose)

    def setup_feeds_buildinfo(self) -> str:
        """Download and configure package feeds.

        Returns:
            The feeds configuration content.
        """
        logger.info("Setting up feeds from buildinfo")
        url = f"{self.config.origin_url}/{self.config.target_dir}/feeds.buildinfo"
        feeds = download_text(url)
        # Use mirror instead of git.openwrt.org (often returns 503)
        if self.config.source_mirror:
            feeds = feeds.replace("https://git.openwrt.org/feed/", self.config.source_mirror)
            feeds = feeds.replace("https://git.openwrt.org/project/", self.config.source_mirror)
        (self.config.rebuild_dir / "feeds.conf").write_text(feeds)
        logger.debug(f"Feeds config:\n{feeds}")
        return feeds

    def setup_version_buildinfo(self) -> tuple[str, str]:
        """Download version buildinfo and extract commit info.

        Returns:
            Tuple of (commit_string, commit_hash).
        """
        logger.info("Setting up version from buildinfo")
        url = f"{self.config.origin_url}/{self.config.target_dir}/version.buildinfo"
        self._commit_string = download_text(url).strip()
        logger.info(f"Remote version: {self._commit_string}")

        # Parse commit hash from version string (e.g., "r12345-abc1234567")
        self._commit = self._commit_string.split("-")[1]
        return self._commit_string, self._commit

    def setup_config_buildinfo(self) -> None:
        """Download and configure build options."""
        logger.info("Setting up config from buildinfo")
        url = f"{self.config.origin_url}/{self.config.target_dir}/config.buildinfo"
        config_content = download_text(url)

        # Add our overrides to speed up the build
        config_overrides = """
CONFIG_COLLECT_KERNEL_DEBUG=n
CONFIG_IB=n
CONFIG_SDK=n
CONFIG_BPF_TOOLCHAIN_HOST=y
CONFIG_MAKE_TOOLCHAIN=n
"""
        (self.config.rebuild_dir / ".config").write_text(config_content + config_overrides)
        self.make("defconfig")

    def setup_kernel_magic(self) -> str:
        """Determine kernel version and magic string.

        Gets the kernel version prefix from the local build, then looks up
        the actual vermagic from the origin server's kmods directory.

        Returns:
            The kernel version string (e.g., "6.12.63-1-abc123def").
        """
        logger.info("Determining kernel version")
        result = self.runner.run(
            [
                "make",
                "--no-print-directory",
                "-C",
                "target/linux/",
                "val.LINUX_VERSION",
                "val.LINUX_RELEASE",
            ],
            capture=True,
            env={
                "TOPDIR": str(self.config.rebuild_dir),
                "INCLUDE_DIR": str(self.config.rebuild_dir / "include"),
            },
        )
        # Get version prefix like "6.12.63-1"
        version_prefix = "-".join(result.stdout.strip().splitlines())
        logger.info(f"Kernel version prefix: {version_prefix}")

        # Fetch the actual vermagic from origin's kmods directory
        kmods_url = f"{self.config.origin_url}/{self.config.target_dir}/kmods/"
        try:
            kmods_listing = download_text(kmods_url)
            # Parse directory listing for matching kernel version
            # Look for href="6.12.63-1-<hash>/" pattern
            pattern = rf'href="({re.escape(version_prefix)}-[a-f0-9]+)/"'
            matches = re.findall(pattern, kmods_listing)
            if matches:
                # Use the most recent (last) match if there are multiple
                self._kernel_version = matches[-1]
                logger.info(f"Found kernel version from origin: {self._kernel_version}")
            else:
                logger.warning(f"No kmod directory found for {version_prefix}, using prefix")
                self._kernel_version = f"{version_prefix}-unknown"
        except Exception as e:
            logger.warning(f"Could not fetch kmods listing: {e}, using local prefix")
            self._kernel_version = f"{version_prefix}-unknown"

        return self._kernel_version

    def get_arch_packages(self) -> str:
        """Get the architecture packages string.

        Returns:
            The ARCH_PACKAGES value.
        """
        result = self.runner.run(
            ["make", "--no-print-directory", "val.ARCH_PACKAGES"],
            capture=True,
            env={
                "TOPDIR": str(self.config.rebuild_dir),
                "INCLUDE_DIR": str(self.config.rebuild_dir / "include"),
            },
        )
        return result.stdout.strip()

    def setup_downloads(self) -> None:
        """Setup download directory symlink if needed."""
        dl_in_tree = self.config.rebuild_dir / "dl"
        if dl_in_tree != self.config.dl_dir and not self.config.dl_dir.exists():
            logger.info(f"Creating symlink {dl_in_tree} -> {self.config.dl_dir}")
            self.config.dl_dir.mkdir(parents=True, exist_ok=True)
            if not dl_in_tree.exists():
                symlink(self.config.dl_dir.absolute(), dl_in_tree)

    def update_feeds(self) -> None:
        """Update and install package feeds."""
        logger.info("Updating feeds")
        self.runner.run(["./scripts/feeds", "update"], capture=True)
        self.runner.run(["./scripts/feeds", "install", "-a"], capture=True)

    def download_sources(self) -> None:
        """Download all source packages."""
        logger.info("Downloading sources")
        self.setup_downloads()
        self.make("download")

    def build_toolchain(self) -> None:
        """Build the toolchain."""
        logger.info("Building toolchain")
        self.make("tools/tar/compile")
        self.make("tools/install")
        self.make("toolchain/install")

    def build_target(self) -> None:
        """Build the target system."""
        logger.info("Building target")
        self.make("target/compile")

    def build_packages(self) -> None:
        """Build all packages."""
        logger.info("Building packages")
        self.make("package/compile")
        self.make("package/install")
        self.make("package/index", "CONFIG_SIGNED_PACKAGES=")

    def build_images(self) -> None:
        """Build firmware images."""
        logger.info("Building images")
        self.make("target/install")

    def generate_metadata(self) -> None:
        """Generate build metadata files."""
        logger.info("Generating metadata")
        self.make("buildinfo", "V=s")
        self.make("json_overview_image_info", "V=s", jobs=1)
        self.make("checksum", "V=s")

    def full_build(self) -> None:
        """Run a complete build from source to images."""
        self.build_toolchain()
        self.build_target()
        self.build_packages()
        self.build_images()
        self.generate_metadata()
