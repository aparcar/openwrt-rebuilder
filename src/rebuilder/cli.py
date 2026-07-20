"""Command-line interface for the rebuilder.

Two build subcommands produce rebuilt artifacts into ``--output`` for an external
verifier (rebuilderd) to compare:

  * ``firmware`` — rebuild a whole target from source
  * ``package``  — rebuild a single apk package via the SDK

Everything is passed as CLI parameters; the tool reads no environment variables.
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

from rebuilder import __version__
from rebuilder.config import Config
from rebuilder.core.build import OpenWrtBuilder
from rebuilder.core.git import GitRepository
from rebuilder.core.package import PackageRebuilder, SdkConfig


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
        description="Rebuild OpenWrt firmware and packages for reproducibility checks",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # firmware: rebuild a whole target from source
    fw = subparsers.add_parser("firmware", help="Rebuild a firmware target from source")
    fw.add_argument("--target", required=True, help="Target/subtarget, e.g. x86/64")
    fw.add_argument("--release", required=True, help="Release, e.g. SNAPSHOT or 24.10.0")
    fw.add_argument(
        "--output", required=True, type=Path, help="Directory to write rebuilt artifacts into"
    )
    fw.add_argument("-j", "--jobs", type=int, default=None, help="Number of parallel build jobs")
    fw.add_argument(
        "--build-dir", type=Path, default=None, help="Build tree (default: ./build/<release>)"
    )
    fw.add_argument("--dl-dir", type=Path, default=None, help="Source download cache")
    fw.add_argument("--source-mirror", default=None, help="Git mirror for OpenWrt sources")
    fw.add_argument("--origin-url", default=None, help="Origin URL for published OpenWrt builds")

    # package: rebuild a single apk package via the SDK
    pkg = subparsers.add_parser("package", help="Rebuild a single apk package via the SDK")
    pkg.add_argument("--package", required=True, help="apk filename, e.g. tmate-2.4.0-r3.apk")
    pkg.add_argument("--target", required=True, help="Target/subtarget of the SDK, e.g. x86/64")
    pkg.add_argument("--release", required=True, help="Release, e.g. SNAPSHOT or 24.10.0")
    pkg.add_argument(
        "--output", required=True, type=Path, help="Directory to write the rebuilt .apk into"
    )
    pkg.add_argument("--upstream", default=None, help="Base URL for downloads.openwrt.org")
    pkg.add_argument("--sdk-cache", type=Path, default=None, help="Cache dir for verified SDKs")
    pkg.add_argument("--dl-dir", type=Path, default=None, help="OpenWrt source download cache")
    pkg.add_argument("--keyring-dir", type=Path, default=None, help="Dir of OpenWrt GPG keys")

    return parser.parse_args(args)


def _publish_artifacts(bin_dir: Path, output_dir: Path) -> None:
    """Copy the rebuilt artifacts (flat) into the output dir for the verifier."""
    logger = logging.getLogger(__name__)
    if not bin_dir.is_dir():
        logger.warning("No artifacts under %s; leaving output empty for comparison", bin_dir)
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in bin_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, output_dir / item.name)
            count += 1
    logger.info("Published %d artifacts to %s", count, output_dir)


def _publish_logs(logs_dir: Path, dest: Path) -> None:
    """Copy OpenWrt's per-package build logs alongside the artifacts, if any."""
    if logs_dir.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(logs_dir, dest)


def run_firmware(args: argparse.Namespace) -> int:
    """Rebuild a firmware target from source into ``args.output``.

    Builds exactly the way the buildbots do (full history checkout, pinned feeds,
    restored release .config) but does no comparison — the verifier compares the
    published files against ``args.output`` itself.
    """
    logger = logging.getLogger(__name__)

    kwargs: dict[str, Any] = {"target": args.target, "version": args.release}
    if args.build_dir:
        kwargs["rebuild_dir"] = args.build_dir
    if args.dl_dir:
        kwargs["dl_dir"] = args.dl_dir
    if args.jobs:
        kwargs["jobs"] = args.jobs
    if args.source_mirror:
        kwargs["source_mirror"] = args.source_mirror
    if args.origin_url:
        kwargs["origin_url"] = args.origin_url
    config = Config(**kwargs)
    # Keep build logs under the build tree so they're cleaned up with it.
    config.results_dir = config.rebuild_dir / "results"

    errors = config.validate()
    if errors:
        for error in errors:
            logger.error("Configuration error: %s", error)
        return 1

    logger.info("=== openwrt firmware rebuild ===")
    logger.info("target:  %s", config.target)
    logger.info("release: %s", config.version)
    logger.info("output:  %s", args.output)

    try:
        git = GitRepository(config)
        git.clone()

        builder = OpenWrtBuilder(config)
        _, commit = builder.setup_version_buildinfo()
        builder.setup_feeds_buildinfo()
        git.checkout(commit)
        builder.update_feeds()

        patches_dir = Path.cwd() / "patches" / config.version
        if patches_dir.exists():
            git.apply_patches(patches_dir)

        builder.setup_config_buildinfo()
        builder.download_sources()
        builder.full_build()

        _publish_artifacts(config.bin_path / "targets" / config.target, args.output)
        return 0
    except Exception as e:
        logger.exception(f"Firmware rebuild failed: {e}")
        return 1
    finally:
        _publish_logs(config.results_dir / "logs", args.output / "logs")


def run_package(args: argparse.Namespace) -> int:
    """Rebuild a single apk package into ``args.output``.

    Returns 0 even when no artifact is produced (the verifier records BAD rather
    than a hard failure).
    """
    logger = logging.getLogger(__name__)

    sdk_kwargs: dict[str, Any] = {}
    if args.upstream:
        sdk_kwargs["upstream"] = args.upstream
    if args.sdk_cache:
        sdk_kwargs["sdk_cache"] = args.sdk_cache
    if args.dl_dir:
        sdk_kwargs["dl_dir"] = args.dl_dir
    if args.keyring_dir:
        sdk_kwargs["keyring_dir"] = args.keyring_dir

    try:
        rebuilder = PackageRebuilder(SdkConfig(**sdk_kwargs))
        result = rebuilder.rebuild(args.package, args.target, args.release, args.output)
        if result is None:
            logger.warning("No artifact produced; leaving output empty for comparison")
        return 0
    except Exception as e:
        logger.exception(f"Package rebuild failed: {e}")
        return 1


def main(args: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    parsed = parse_args(args)
    setup_logging(parsed.verbose)
    logger = logging.getLogger(__name__)

    if parsed.command == "firmware":
        return run_firmware(parsed)
    if parsed.command == "package":
        return run_package(parsed)

    logger.error("no command given; use 'firmware' or 'package'")
    return 1


if __name__ == "__main__":
    sys.exit(main())
