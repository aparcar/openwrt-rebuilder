"""Command-line interface for the rebuilder."""

import argparse
import logging
import sys

from rebuilder import __version__
from rebuilder.config import Config


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

    # TODO: Run the actual rebuild
    logger.info(f"Starting rebuild for {config.target} @ {config.version}")
    logger.info("Note: Full rebuild logic not yet migrated to new structure")
    logger.info("Use rebuild.py directly for now")

    return 0


if __name__ == "__main__":
    sys.exit(main())
