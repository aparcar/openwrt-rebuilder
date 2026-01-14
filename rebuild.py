#!/usr/bin/env python3
#
# Copyright © 2022 - 2025 Paul Spooren <mail@aparcar.org>
#
# Based on the reproducible_openwrt.sh
#   © 2014-2019 Holger Levsen <holger@layer-acht.org>
#   © 2015 Reiner Herrmann <reiner@reiner-h.de>
#   © 2016-2018 Alexander Couzens <lynxis@fe80.eu>
#
# Released under the GPLv2

"""
OpenWrt Reproducible Build Script

This script rebuilds OpenWrt firmware and compares it against official builds
to verify reproducibility.

Usage:
    TARGET=x86/64 VERSION=SNAPSHOT python rebuild.py

Environment Variables:
    TARGET        - Target architecture (default: x86/64)
    VERSION       - OpenWrt version (default: SNAPSHOT)
    REBUILD_DIR   - Build directory
    ORIGIN_URL    - Official builds URL
    OPENWRT_GIT   - Git repository URL
    USE_DIFFOSCOPE - Enable diffoscope analysis
    j             - Parallel jobs
    RESULTS_DIR   - Results output directory
    DL_PATH       - Downloads directory
"""

import json
import logging
import sys
from pathlib import Path

# Import from the new modular package
from src.rebuilder.config import Config
from src.rebuilder.core.build import OpenWrtBuilder
from src.rebuilder.core.compare import Comparator
from src.rebuilder.core.download import discover_kernel_version, download_text
from src.rebuilder.core.git import GitRepository
from src.rebuilder.diffoscope import DiffoscopeRunner
from src.rebuilder.models import Suite
from src.rebuilder.parsers import parse_profiles, parse_sha256sums
from src.rebuilder.reporting import write_rbvf_output

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class Rebuilder:
    """Main rebuilder orchestrator using the modular package."""

    def __init__(self, config: Config | None = None):
        """Initialize the rebuilder.

        Args:
            config: Optional configuration. If not provided, reads from environment.
        """
        self.config = config or Config.from_env()
        self.suite = Suite()
        self.git: GitRepository | None = None
        self.builder: OpenWrtBuilder | None = None
        self._origin_kernel_version: str | None = None

        # Validate configuration
        errors = self.config.validate()
        if errors:
            for error in errors:
                logger.error(f"Config error: {error}")
            raise ValueError("Invalid configuration")

        logger.info(f"Target: {self.config.target}")
        logger.info(f"Version: {self.config.version}")
        logger.info(f"Branch: {self.config.branch}")

    def get_origin_kernel_version(self) -> str:
        """Get the kernel version from the origin server.

        Returns:
            The kernel version string for kmods URLs.
        """
        if self._origin_kernel_version is None:
            self._origin_kernel_version = discover_kernel_version(
                self.config.origin_url, self.config.target_dir
            )
        return self._origin_kernel_version

    def setup_repository(self) -> None:
        """Clone and setup the OpenWrt repository."""
        logger.info("Setting up repository...")
        self.git = GitRepository(self.config)
        self.git.clone()

    def setup_build(self) -> None:
        """Setup build configuration from buildinfo files."""
        logger.info("Setting up build configuration...")
        self.builder = OpenWrtBuilder(self.config)

        # Get version info and checkout
        commit_string, commit = self.builder.setup_version_buildinfo()
        logger.info(f"Version: {commit_string}, Commit: {commit}")

        # Setup feeds
        self.builder.setup_feeds_buildinfo()

        # Checkout the specific commit
        if self.git:
            self.git.checkout(commit)

        # Update and install feeds
        self.builder.update_feeds()

        # Apply patches if any
        patches_dir = Path.cwd() / "patches" / self.config.version
        if self.git and patches_dir.exists():
            self.git.apply_patches(patches_dir)

        # Setup build config
        self.builder.setup_config_buildinfo()

        # Get kernel version
        self.builder.setup_kernel_magic()

    def download_sources(self) -> None:
        """Download all source packages."""
        if self.builder:
            self.builder.download_sources()

    def build(self) -> None:
        """Run the full build process."""
        if self.builder:
            self.builder.full_build()

    def get_origin_profiles(self) -> dict[str, str]:
        """Download and parse origin profiles.json.

        Returns:
            Dictionary of image filename to SHA256 hash.
        """
        url = f"{self.config.origin_url}/{self.config.target_dir}/profiles.json"
        content = download_text(url)
        return parse_profiles(content)

    def compare_results(self, origin_profiles: dict[str, str]) -> None:
        """Compare rebuild results against origin.

        Args:
            origin_profiles: Origin image checksums.
        """
        logger.info("Comparing results...")
        comparator = Comparator(self.config, self.suite)

        # Compare profiles/images
        profiles_path = self.config.bin_path / "targets" / self.config.target / "profiles.json"
        if profiles_path.exists():
            comparator.compare_profiles(origin_profiles, profiles_path)

        # Compare target packages
        target_index = (
            self.config.bin_path / "targets" / self.config.target / "packages" / "index.json"
        )
        target_sums = self.config.bin_path / "targets" / self.config.target / "sha256sums"
        if target_index.exists() and target_sums.exists():
            # Download origin sha256sums
            origin_url = f"{self.config.origin_url}/{self.config.target_dir}/sha256sums"
            origin_content = download_text(origin_url)
            origin_sums = parse_sha256sums(origin_content)
            rebuild_sums = parse_sha256sums(target_sums.read_text())

            comparator.compare_packages(
                origin_sums,
                rebuild_sums,
                target_index,
                f"targets/{self.config.target}/packages",
            )

        # Compare base packages
        if target_index.exists():
            arch = json.loads(target_index.read_text()).get("architecture", "")
            base_index = self.config.bin_path / "packages" / arch / "base" / "index.json"
            base_sums = self.config.bin_path / "packages" / arch / "sha256sums"

            if base_index.exists() and base_sums.exists():
                origin_base_url = (
                    f"{self.config.origin_url}/{self.config.release_dir}/packages/{arch}/sha256sums"
                )
                try:
                    origin_base_content = download_text(origin_base_url)
                    origin_base_sums = parse_sha256sums(origin_base_content)
                    rebuild_base_sums = parse_sha256sums(base_sums.read_text())

                    comparator.compare_packages(
                        origin_base_sums,
                        rebuild_base_sums,
                        base_index,
                        f"packages/{arch}/base",
                    )
                except Exception as e:
                    logger.warning(f"Could not compare base packages: {e}")

    def run_diffoscope(self) -> None:
        """Run diffoscope on unreproducible results."""
        if not self.config.use_diffoscope:
            logger.info("Diffoscope disabled, skipping...")
            return

        logger.info("Running diffoscope analysis...")
        # Use origin kernel version for downloading origin files
        kernel_version = self.get_origin_kernel_version()
        runner = DiffoscopeRunner(self.config, kernel_version=kernel_version)

        # Collect all unreproducible results
        unreproducible = self.suite.packages.unreproducible + self.suite.images.unreproducible

        if unreproducible:
            runner.run_parallel(unreproducible)
        else:
            logger.info("No unreproducible results to analyze")

    def save_results(self) -> Path:
        """Save results to JSON file.

        Returns:
            Path to the output file.
        """
        logger.info("Saving results...")
        self.config.results_dir.mkdir(parents=True, exist_ok=True)
        (self.config.results_dir / "base").mkdir(exist_ok=True)

        return write_rbvf_output(self.config, self.suite)

    def run(self) -> int:
        """Run the full rebuild workflow.

        Returns:
            Exit code (0 for success).
        """
        try:
            # Setup
            self.setup_repository()
            self.setup_build()
            self.download_sources()

            # Get origin profiles before building
            origin_profiles = self.get_origin_profiles()

            # Build
            self.build()

            # Compare and analyze
            self.compare_results(origin_profiles)
            self.run_diffoscope()

            # Save results
            output_path = self.save_results()
            logger.info(f"Results written to {output_path}")

            # Summary
            pkg_stats = self.suite.packages.stats()
            img_stats = self.suite.images.stats()
            logger.info(
                f"Packages: {pkg_stats['reproducible']} reproducible, "
                f"{pkg_stats['unreproducible']} unreproducible, "
                f"{pkg_stats['notfound']} not found"
            )
            logger.info(
                f"Images: {img_stats['reproducible']} reproducible, "
                f"{img_stats['unreproducible']} unreproducible, "
                f"{img_stats['notfound']} not found"
            )

            return 0

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            return 130
        except Exception as e:
            logger.exception(f"Rebuild failed: {e}")
            return 1


def rebuild() -> int:
    """Main entry point for the rebuild process.

    Returns:
        Exit code.
    """
    rebuilder = Rebuilder()
    return rebuilder.run()


if __name__ == "__main__":
    sys.exit(rebuild())
