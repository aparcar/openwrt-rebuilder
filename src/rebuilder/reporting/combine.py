"""Combine results from multiple rebuild runs."""

import json
import logging
from pathlib import Path
from typing import Any

from rebuilder.reporting.html import BuildInfo, HTMLReportGenerator

logger = logging.getLogger(__name__)

# Type aliases for clarity
TargetData = dict[str, dict[str, list[dict[str, Any]]]]
CombinedData = dict[str, dict[str, TargetData]]


def collect_results(results_dir: Path) -> tuple[CombinedData, list[Path]]:
    """Collect all stats.json files and HTML files from a directory.

    Args:
        results_dir: Directory to search for stats.json files.

    Returns:
        Tuple of (combined_data dict, list of HTML file paths).
    """
    combined_data: CombinedData = {}
    html_files: list[Path] = []

    for stats_path in results_dir.glob("**/stats.json"):
        logger.info(f"Found: {stats_path}")
        results_subdir = stats_path.parent

        try:
            with open(stats_path) as f:
                stats = json.load(f)

            version = stats.get("version", "unknown")
            target = stats.get("target", "unknown")

            # Detect if this is a snapshot build by checking directory structure
            # Path could be: results/SNAPSHOT/r28532-abc123def/x86/64/stats.json
            rel_path = stats_path.relative_to(results_dir)
            path_parts = rel_path.parts

            # Check if version contains SNAPSHOT and path has version code
            if "SNAPSHOT" in version and len(path_parts) >= 4:
                # Structure: VERSION/VERSION_CODE/TARGET.../stats.json
                version_code = path_parts[1]  # e.g., r28532-abc123def
                version_key = f"{version}/{version_code}"
            else:
                version_key = version

            # Load packages and images
            packages_path = results_subdir / "packages.json"
            images_path = results_subdir / "images.json"

            target_data: TargetData = {"packages": {}, "images": {}}

            if packages_path.exists():
                packages = json.loads(packages_path.read_text())
                # Group by status
                for pkg in packages:
                    status = pkg.get("status", "UNKWN")
                    if status not in target_data["packages"]:
                        target_data["packages"][status] = []
                    target_data["packages"][status].append(pkg)

            if images_path.exists():
                images = json.loads(images_path.read_text())
                # Group by status
                for img in images:
                    status = img.get("status", "UNKWN")
                    if status not in target_data["images"]:
                        target_data["images"][status] = []
                    target_data["images"][status].append(img)

            # Merge the data
            if version_key not in combined_data:
                combined_data[version_key] = {}
            combined_data[version_key][target] = target_data

            # Collect HTML files (diffoscope reports)
            for html_file in results_subdir.glob("**/*.html"):
                if html_file.name != "index.html":
                    html_files.append(html_file)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse {stats_path}: {e}")
        except Exception as e:
            logger.error(f"Error reading {stats_path}: {e}")

    return combined_data, html_files


def collect_existing_results(output_dir: Path) -> CombinedData:
    """Collect existing results from the output directory (gh-pages).

    Args:
        output_dir: Directory with existing results (e.g., combined_results/).

    Returns:
        Combined data dict from existing results.
    """
    existing_data: CombinedData = {}

    # Look for existing stats.json files in the output directory structure
    for stats_path in output_dir.glob("**/stats.json"):
        # Skip if in diffoscope directory
        if "diffoscope" in str(stats_path):
            continue

        logger.info(f"Found existing: {stats_path}")

        try:
            with open(stats_path) as f:
                stats = json.load(f)

            version = stats.get("version", "unknown")
            target = stats.get("target", "unknown")

            # Determine version key from path
            rel_path = stats_path.relative_to(output_dir)
            path_parts = rel_path.parts

            # Check for snapshot structure: SNAPSHOT/r28532-abc123def/x86/64/stats.json
            if "SNAPSHOT" in version and len(path_parts) >= 4:
                version_key = f"{path_parts[0]}/{path_parts[1]}"
            else:
                version_key = version

            # Load packages and images
            packages_path = stats_path.parent / "packages.json"
            images_path = stats_path.parent / "images.json"

            target_data: TargetData = {"packages": {}, "images": {}}

            if packages_path.exists():
                packages = json.loads(packages_path.read_text())
                for pkg in packages:
                    status = pkg.get("status", "UNKWN")
                    if status not in target_data["packages"]:
                        target_data["packages"][status] = []
                    target_data["packages"][status].append(pkg)

            if images_path.exists():
                images = json.loads(images_path.read_text())
                for img in images:
                    status = img.get("status", "UNKWN")
                    if status not in target_data["images"]:
                        target_data["images"][status] = []
                    target_data["images"][status].append(img)

            if version_key not in existing_data:
                existing_data[version_key] = {}
            existing_data[version_key][target] = target_data

        except Exception as e:
            logger.warning(f"Error reading existing {stats_path}: {e}")

    return existing_data


def combine_results(
    results_dir: Path,
    output_dir: Path,
) -> dict[str, int]:
    """Combine rebuild results and generate HTML reports.

    Args:
        results_dir: Directory containing result artifacts.
        output_dir: Directory to write combined output.

    Returns:
        Overall statistics dictionary.
    """
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect existing results from output dir (gh-pages content)
    logger.info(f"Checking for existing results in {output_dir}")
    existing_data = collect_existing_results(output_dir)
    if existing_data:
        logger.info(f"Found {len(existing_data)} existing version(s)")

    # Collect new results
    logger.info(f"Collecting new results from {results_dir}")
    combined_data, html_files = collect_results(results_dir)

    if not combined_data and not existing_data:
        logger.error(f"No results found in {results_dir} or {output_dir}")
        return {"good": 0, "bad": 0, "unknown": 0}

    # Merge existing data with new data (new data overwrites existing for same version/target)
    for version, targets in existing_data.items():
        if version not in combined_data:
            combined_data[version] = targets
        else:
            # Merge targets, new results overwrite existing
            for target, target_data in targets.items():
                if target not in combined_data[version]:
                    combined_data[version][target] = target_data

    logger.info(f"Total: {len(combined_data)} version(s), {len(html_files)} new diffoscope reports")

    # Generate HTML reports
    logger.info("Generating HTML reports...")
    generator = HTMLReportGenerator(output_dir)
    build_info = BuildInfo.from_environment()
    stats = generator.generate_all(combined_data, results_dir, build_info)

    # Print summary
    total = sum(stats.values())
    percent = (stats["good"] / total * 100) if total > 0 else 0

    logger.info("=" * 60)
    logger.info(f"Summary: {percent:.1f}% GOOD ({stats['good']}/{total})")
    logger.info(f"  GOOD: {stats['good']}")
    logger.info(f"  BAD: {stats['bad']}")
    logger.info(f"  UNKNOWN: {stats['unknown']}")
    logger.info("=" * 60)

    return stats
