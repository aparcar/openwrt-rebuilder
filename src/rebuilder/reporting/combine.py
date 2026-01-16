"""Combine results from multiple rebuild runs."""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict, cast

from rebuilder.reporting.html import BuildInfo, HTMLReportGenerator

logger = logging.getLogger(__name__)

# Type aliases for clarity
TargetData = dict[str, dict[str, list[dict[str, Any]]]]
CombinedData = dict[str, dict[str, TargetData]]

# Maximum number of history entries to keep per version
MAX_HISTORY_ENTRIES = 50


class TargetStats(TypedDict):
    """Statistics for a single target."""

    good: int
    bad: int
    unknown: int


class HistoryEntry(TypedDict, total=False):
    """A single entry in the version history."""

    timestamp: str
    version_code: str | None  # Only for SNAPSHOT builds
    run_id: str
    commit: str
    stats: TargetStats
    targets: dict[str, TargetStats]


class VersionHistory(TypedDict):
    """History data for a version."""

    version: str
    entries: list[HistoryEntry]


def get_version_slug(version: str) -> str:
    """Convert a version string to a filesystem-safe slug.

    Args:
        version: Version string (e.g., "25.12.1", "SNAPSHOT/r28532-abc").

    Returns:
        Filesystem-safe slug.
    """
    return version.replace(".", "_").replace("/", "_")


def get_base_version(version_key: str) -> tuple[str, str | None]:
    """Extract base version and version code from a version key.

    Args:
        version_key: Full version key (e.g., "SNAPSHOT/r28532-abc" or "25.12.1").

    Returns:
        Tuple of (base_version, version_code). version_code is None for releases.
    """
    if "SNAPSHOT" in version_key and "/" in version_key:
        parts = version_key.split("/", 1)
        return parts[0], parts[1]
    return version_key, None


def load_history(output_dir: Path, base_version: str) -> VersionHistory:
    """Load existing history for a version.

    Args:
        output_dir: Output directory containing history files.
        base_version: Base version (e.g., "SNAPSHOT", "25.12.1").

    Returns:
        Version history dict, empty if not found.
    """
    version_slug = get_version_slug(base_version)
    history_path = output_dir / version_slug / "history.json"

    if history_path.exists():
        try:
            with open(history_path) as f:
                data: VersionHistory = json.load(f)
                logger.info(f"Loaded history with {len(data.get('entries', []))} entries")
                return data
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to load history from {history_path}: {e}")

    return {"version": base_version, "entries": []}


def save_history(output_dir: Path, base_version: str, history: VersionHistory) -> None:
    """Save history for a version.

    Args:
        output_dir: Output directory for history files.
        base_version: Base version (e.g., "SNAPSHOT", "25.12.1").
        history: History data to save.
    """
    version_slug = get_version_slug(base_version)
    history_dir = output_dir / version_slug
    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / "history.json"

    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)

    logger.info(f"Saved history with {len(history['entries'])} entries to {history_path}")


def update_history(
    history: VersionHistory,
    stats: TargetStats,
    targets: dict[str, TargetStats],
    version_code: str | None,
    build_info: BuildInfo,
    timestamp: str | None = None,
) -> VersionHistory:
    """Add a new entry to the version history.

    Args:
        history: Existing history to update.
        stats: Overall stats for this run.
        targets: Per-target stats for this run.
        version_code: Version code (for SNAPSHOT builds) or None.
        build_info: Build metadata.
        timestamp: Optional timestamp override (defaults to now).

    Returns:
        Updated history with new entry added.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    new_entry: HistoryEntry = {
        "timestamp": timestamp,
        "version_code": version_code,
        "run_id": build_info.run_id,
        "commit": build_info.commit,
        "stats": stats,
        "targets": targets,
    }

    # Check if we're updating an existing entry (same version_code for SNAPSHOT)
    existing_idx = None
    if version_code:
        for idx, entry in enumerate(history["entries"]):
            if entry.get("version_code") == version_code:
                existing_idx = idx
                break

    if existing_idx is not None:
        # Update existing entry
        history["entries"][existing_idx] = new_entry
        logger.info(f"Updated existing history entry for {version_code}")
    else:
        # Add new entry at the beginning
        history["entries"].insert(0, new_entry)
        logger.info(f"Added new history entry (version_code={version_code})")

    # Cap the number of entries
    if len(history["entries"]) > MAX_HISTORY_ENTRIES:
        removed = len(history["entries"]) - MAX_HISTORY_ENTRIES
        history["entries"] = history["entries"][:MAX_HISTORY_ENTRIES]
        logger.info(f"Removed {removed} old history entries (cap: {MAX_HISTORY_ENTRIES})")

    return history


def cleanup_old_artifacts(
    output_dir: Path,
    base_version: str,
    current_version_code: str | None,
) -> int:
    """Remove diffoscope reports and artifacts from previous runs.

    For SNAPSHOT builds, removes files from old version codes.
    For releases, cleans up all old diffoscope/artifacts (keeping only current run).

    Args:
        output_dir: Output directory containing artifacts.
        base_version: Base version (e.g., "SNAPSHOT", "25.12.1").
        current_version_code: Current version code to keep (for SNAPSHOT).

    Returns:
        Number of files/directories removed.
    """
    removed_count = 0

    # For now, we'll clean the entire diffoscope and artifacts directories
    # since they'll be repopulated with current run data
    # In a more sophisticated implementation, we'd track which files belong to which run

    diffoscope_dir = output_dir / "diffoscope"
    artifacts_dir = output_dir / "artifacts"

    # Clean diffoscope reports
    if diffoscope_dir.exists():
        for item in diffoscope_dir.iterdir():
            if item.is_file():
                item.unlink()
                removed_count += 1
            elif item.is_dir():
                shutil.rmtree(item)
                removed_count += 1

    # Clean artifacts
    if artifacts_dir.exists():
        for item in artifacts_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
                removed_count += 1
            elif item.is_file():
                item.unlink()
                removed_count += 1

    if removed_count > 0:
        logger.info(f"Cleaned up {removed_count} old diffoscope/artifact items")

    return removed_count


class ResultMetadata(TypedDict):
    """Metadata extracted from results."""

    timestamp: str | None
    version_code: str | None


def collect_results(
    results_dir: Path,
) -> tuple[CombinedData, list[Path], dict[str, ResultMetadata]]:
    """Collect all stats.json files and HTML files from a directory.

    Args:
        results_dir: Directory to search for stats.json files.

    Returns:
        Tuple of (combined_data dict, list of HTML file paths, metadata per version).
    """
    combined_data: CombinedData = {}
    html_files: list[Path] = []
    metadata: dict[str, ResultMetadata] = {}

    for stats_path in results_dir.glob("**/stats.json"):
        logger.info(f"Found: {stats_path}")
        results_subdir = stats_path.parent

        try:
            with open(stats_path) as f:
                stats = json.load(f)

            version = stats.get("version", "unknown")
            target = stats.get("target", "unknown")
            generated_at = stats.get("generated_at")

            # Detect if this is a snapshot build by checking directory structure
            # Path could be: results/SNAPSHOT/r28532-abc123def/x86/64/stats.json
            rel_path = stats_path.relative_to(results_dir)
            path_parts = rel_path.parts

            # Check if version contains SNAPSHOT and path has version code
            version_code: str | None = None
            if "SNAPSHOT" in version and len(path_parts) >= 4:
                # Structure: VERSION/VERSION_CODE/TARGET.../stats.json
                version_code = path_parts[1]  # e.g., r28532-abc123def
                version_key = f"{version}/{version_code}"
            else:
                version_key = version

            # Store metadata for this version
            if version_key not in metadata:
                metadata[version_key] = {
                    "timestamp": generated_at,
                    "version_code": version_code,
                }

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

    return combined_data, html_files, metadata


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


def calculate_target_stats(target_data: TargetData) -> TargetStats:
    """Calculate stats for a single target.

    Args:
        target_data: Target data with packages and images.

    Returns:
        Statistics dictionary.
    """
    good = 0
    bad = 0
    unknown = 0

    for category in ["packages", "images"]:
        if category in target_data:
            good += len(target_data[category].get("GOOD", []))
            bad += len(target_data[category].get("BAD", []))
            unknown += len(target_data[category].get("UNKWN", []))

    return {"good": good, "bad": bad, "unknown": unknown}


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

    # Get build info early for history tracking
    build_info = BuildInfo.from_environment()

    # Collect existing results from output dir (gh-pages content)
    logger.info(f"Checking for existing results in {output_dir}")
    existing_data = collect_existing_results(output_dir)
    if existing_data:
        logger.info(f"Found {len(existing_data)} existing version(s)")

    # Collect new results
    logger.info(f"Collecting new results from {results_dir}")
    combined_data, html_files, result_metadata = collect_results(results_dir)

    if not combined_data and not existing_data:
        logger.error(f"No results found in {results_dir} or {output_dir}")
        return {"good": 0, "bad": 0, "unknown": 0}

    # Track which base versions have new results for history updates
    versions_with_new_results: dict[str, tuple[str | None, str | None]] = {}
    for version_key, meta in result_metadata.items():
        base_version, version_code = get_base_version(version_key)
        versions_with_new_results[base_version] = (version_code, meta.get("timestamp"))

    # Update history for versions with new results
    all_histories: dict[str, VersionHistory] = {}
    for base_version, (version_code, timestamp) in versions_with_new_results.items():
        # Load existing history
        history = load_history(output_dir, base_version)

        # Calculate stats for new results
        # Find all version keys that match this base version
        matching_keys = [k for k in combined_data.keys() if get_base_version(k)[0] == base_version]

        # Aggregate stats across all matching version keys
        overall_stats: TargetStats = {"good": 0, "bad": 0, "unknown": 0}
        target_stats: dict[str, TargetStats] = {}

        for version_key in matching_keys:
            for target, target_data in combined_data[version_key].items():
                t_stats = calculate_target_stats(target_data)
                target_stats[target] = t_stats
                overall_stats["good"] += t_stats["good"]
                overall_stats["bad"] += t_stats["bad"]
                overall_stats["unknown"] += t_stats["unknown"]

        # Update history with new entry
        history = update_history(
            history,
            overall_stats,
            target_stats,
            version_code,
            build_info,
            timestamp,
        )
        all_histories[base_version] = history

        # Clean up old diffoscope/artifacts before adding new ones
        cleanup_old_artifacts(output_dir, base_version, version_code)

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

    # Generate HTML reports with history data
    logger.info("Generating HTML reports...")
    generator = HTMLReportGenerator(output_dir)
    # Cast to satisfy type checker (VersionHistory TypedDict is compatible with dict[str, Any])
    histories_for_html = cast(dict[str, dict[str, Any]], all_histories)
    stats = generator.generate_all(combined_data, results_dir, build_info, histories_for_html)

    # Save all updated histories
    for base_version, history in all_histories.items():
        save_history(output_dir, base_version, history)

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
