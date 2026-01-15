"""Command-line interface for the rebuilder."""

import argparse
import json
import logging
import sys
from pathlib import Path

from rebuilder import __version__
from rebuilder.config import Config
from rebuilder.core.build import OpenWrtBuilder
from rebuilder.core.compare import Comparator
from rebuilder.core.download import download_text
from rebuilder.core.git import GitRepository
from rebuilder.diffoscope import DiffoscopeRunner
from rebuilder.models import Suite
from rebuilder.parsers import parse_profiles, parse_sha256sums
from rebuilder.reporting import write_rbvf_output


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="openwrt-rebuilder",
        description="Reproducible builds verification tool for OpenWrt firmware",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "-t",
        "--target",
        default=None,
        help="Target architecture (e.g., x86/64, mediatek/filogic)",
    )

    parser.add_argument(
        "-V",
        "--openwrt-version",
        default=None,
        dest="openwrt_version",
        help="OpenWrt version to rebuild (e.g., SNAPSHOT, 23.05.2)",
    )

    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="Number of parallel build jobs",
    )

    parser.add_argument(
        "--no-diffoscope",
        action="store_true",
        help="Skip diffoscope analysis",
    )

    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate configuration, don't run rebuild",
    )

    return parser.parse_args(args)


def run_rebuild(config: Config) -> int:
    """Run the full rebuild workflow.

    Args:
        config: Rebuild configuration.

    Returns:
        Exit code (0 for success).
    """
    logger = logging.getLogger(__name__)
    suite = Suite()

    try:
        # Setup repository
        logger.info("Setting up repository...")
        git = GitRepository(config)
        git.clone()

        # Setup build
        logger.info("Setting up build configuration...")
        builder = OpenWrtBuilder(config)

        commit_string, commit = builder.setup_version_buildinfo()
        logger.info(f"Version: {commit_string}, Commit: {commit}")

        builder.setup_feeds_buildinfo()
        git.checkout(commit)
        builder.update_feeds()

        # Apply patches if any
        patches_dir = Path.cwd() / "patches" / config.version
        if patches_dir.exists():
            git.apply_patches(patches_dir)

        builder.setup_config_buildinfo()
        builder.setup_kernel_magic()

        # Download sources
        builder.download_sources()

        # Get origin profiles before building
        url = f"{config.origin_url}/{config.target_dir}/profiles.json"
        origin_profiles = parse_profiles(download_text(url))

        # Build
        builder.full_build()

        # Compare results
        logger.info("Comparing results...")
        comparator = Comparator(config, suite)

        profiles_path = config.bin_path / "targets" / config.target / "profiles.json"
        if profiles_path.exists():
            comparator.compare_profiles(origin_profiles, profiles_path)

        target_index = config.bin_path / "targets" / config.target / "packages" / "index.json"
        target_sums = config.bin_path / "targets" / config.target / "sha256sums"
        if target_index.exists() and target_sums.exists():
            origin_url = f"{config.origin_url}/{config.target_dir}/sha256sums"
            origin_sums = parse_sha256sums(download_text(origin_url))
            rebuild_sums = parse_sha256sums(target_sums.read_text())
            comparator.compare_packages(
                origin_sums, rebuild_sums, target_index, f"targets/{config.target}/packages"
            )

        if target_index.exists():
            arch = json.loads(target_index.read_text()).get("architecture", "")
            base_index = config.bin_path / "packages" / arch / "base" / "index.json"
            base_sums = config.bin_path / "packages" / arch / "sha256sums"

            if base_index.exists() and base_sums.exists():
                origin_base_url = (
                    f"{config.origin_url}/{config.release_dir}/packages/{arch}/sha256sums"
                )
                try:
                    origin_base_sums = parse_sha256sums(download_text(origin_base_url))
                    rebuild_base_sums = parse_sha256sums(base_sums.read_text())
                    comparator.compare_packages(
                        origin_base_sums, rebuild_base_sums, base_index, f"packages/{arch}/base"
                    )
                except Exception as e:
                    logger.warning(f"Could not compare base packages: {e}")

        # Run diffoscope
        if config.use_diffoscope:
            logger.info("Running diffoscope analysis...")
            runner = DiffoscopeRunner(config, kernel_version=builder.kernel_version)
            unreproducible = suite.packages.unreproducible + suite.images.unreproducible
            if unreproducible:
                runner.run_parallel(unreproducible)
            else:
                logger.info("No unreproducible results to analyze")

        # Save results
        logger.info("Saving results...")
        config.results_dir.mkdir(parents=True, exist_ok=True)
        (config.results_dir / "base").mkdir(exist_ok=True)
        output_path = write_rbvf_output(config, suite)
        logger.info(f"Results written to {output_path}")

        # Summary
        pkg_stats = suite.packages.stats()
        img_stats = suite.images.stats()
        logger.info(
            f"Packages: {pkg_stats['good']} GOOD, "
            f"{pkg_stats['bad']} BAD, "
            f"{pkg_stats['unknown']} UNKNOWN"
        )
        logger.info(
            f"Images: {img_stats['good']} GOOD, "
            f"{img_stats['bad']} BAD, "
            f"{img_stats['unknown']} UNKNOWN"
        )

        return 0

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Rebuild failed: {e}")
        return 1


def main(args: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    parsed = parse_args(args)
    setup_logging(parsed.verbose)

    logger = logging.getLogger(__name__)

    # Build configuration from args and environment
    config_kwargs = {}
    if parsed.target:
        config_kwargs["target"] = parsed.target
    if parsed.openwrt_version:
        config_kwargs["version"] = parsed.openwrt_version
    if parsed.jobs:
        config_kwargs["jobs"] = parsed.jobs
    if parsed.no_diffoscope:
        config_kwargs["use_diffoscope"] = False

    try:
        config = Config(**config_kwargs)
    except Exception as e:
        logger.error(f"Failed to create configuration: {e}")
        return 1

    # Validate configuration
    errors = config.validate()
    if errors:
        logger.error("Configuration validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        return 1

    if parsed.validate_only:
        logger.info("Configuration is valid")
        logger.info(f"  Target: {config.target}")
        logger.info(f"  Version: {config.version}")
        logger.info(f"  Branch: {config.branch}")
        logger.info(f"  Jobs: {config.jobs}")
        return 0

    # Run the rebuild
    logger.info(f"Starting rebuild for {config.target} @ {config.version}")
    return run_rebuild(config)


if __name__ == "__main__":
    sys.exit(main())
