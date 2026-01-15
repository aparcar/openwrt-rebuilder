"""Configuration management for the rebuilder."""

from dataclasses import dataclass, field
from multiprocessing import cpu_count
from os import environ
from pathlib import Path


@dataclass
class Config:
    """Immutable configuration for a rebuild run."""

    # Target architecture (e.g., "x86/64", "mediatek/filogic")
    target: str = field(default_factory=lambda: environ.get("TARGET", "x86/64").replace("-", "/"))

    # OpenWrt version to rebuild
    version: str = field(default_factory=lambda: environ.get("VERSION", "SNAPSHOT"))

    # Base directory for the build
    rebuild_dir: Path = field(default=None)  # type: ignore[assignment]

    # Downloads directory
    dl_dir: Path = field(default=None)  # type: ignore[assignment]

    # Results output directory
    results_dir: Path = field(default=None)  # type: ignore[assignment]

    # Origin URL for official OpenWrt builds
    origin_url: str = field(
        default_factory=lambda: environ.get("ORIGIN_URL", "https://downloads.openwrt.org")
    )

    # Mirror URL for OpenWrt sources (replaces git.openwrt.org which often returns 503)
    # Use "https://codeberg.org/openwrt/" or "https://github.com/openwrt/"
    source_mirror: str = field(
        default_factory=lambda: environ.get("SOURCE_MIRROR", "https://codeberg.org/openwrt/")
    )

    # Whether to run diffoscope on unreproducible builds
    use_diffoscope: bool = field(default_factory=lambda: bool(environ.get("USE_DIFFOSCOPE", True)))

    # Number of parallel jobs
    jobs: int = field(default_factory=lambda: int(environ.get("j", cpu_count() + 1)))

    def __post_init__(self) -> None:
        """Initialize derived paths after dataclass initialization."""
        if self.rebuild_dir is None:
            self.rebuild_dir = Path(environ.get("REBUILD_DIR", Path.cwd() / "build" / self.version))

        if self.dl_dir is None:
            self.dl_dir = Path(environ.get("DL_PATH", self.rebuild_dir / "dl"))

        if self.results_dir is None:
            self.results_dir = Path(
                environ.get("RESULTS_DIR", Path.cwd() / "results" / self.version / self.target)
            )

    @property
    def openwrt_git(self) -> str:
        """Git URL for the main OpenWrt repository."""
        return f"{self.source_mirror}openwrt.git"

    @property
    def bin_path(self) -> Path:
        """Path to build output binaries."""
        return self.rebuild_dir / "bin"

    @property
    def release_dir(self) -> str:
        """Release directory name on the origin server."""
        if self.version == "SNAPSHOT":
            return "snapshots"
        return f"releases/{self.version}"

    @property
    def target_dir(self) -> str:
        """Full target directory path on the origin server."""
        return f"{self.release_dir}/targets/{self.target}"

    @property
    def branch(self) -> str:
        """Git branch name for this version."""
        if self.version == "SNAPSHOT":
            return "master"
        # e.g., "23.05.2" -> "openwrt-23.05"
        return f"openwrt-{self.version.rsplit('.', maxsplit=1)[0]}"

    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables."""
        return cls()

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors (empty if valid)."""
        errors = []

        if "/" not in self.target:
            errors.append(f"Invalid target format: {self.target} (expected 'arch/subtarget')")

        if not self.origin_url.startswith(("http://", "https://")):
            errors.append(f"Invalid origin URL: {self.origin_url}")

        if self.jobs < 1:
            errors.append(f"Invalid job count: {self.jobs}")

        return errors
