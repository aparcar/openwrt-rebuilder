"""HTML report generation using Jinja2 templates."""

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from os import environ
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

logger = logging.getLogger(__name__)

# Type alias for history data
# Using Any to avoid circular import with combine.py's TypedDict
VersionHistory = dict[str, Any]  # Actually: {"version": str, "entries": list[HistoryEntry]}


@dataclass
class BuildInfo:
    """Build metadata for reports."""

    time: str
    commit: str
    branch: str
    run_id: str

    @classmethod
    def from_environment(cls) -> "BuildInfo":
        """Create build info from GitHub Actions environment variables."""
        return cls(
            time=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            commit=environ.get("GITHUB_SHA", "unknown")[:8],
            branch=environ.get("GITHUB_REF_NAME", "unknown"),
            run_id=environ.get("GITHUB_RUN_ID", "unknown"),
        )


def calculate_stats(data: dict[str, Any]) -> dict[str, int]:
    """Calculate statistics from result data.

    Args:
        data: Dictionary containing packages and/or images results.

    Returns:
        Dictionary with counts for each status (rebuilderd compatible).
    """
    stats = {"good": 0, "bad": 0, "unknown": 0}

    for category in ["packages", "images"]:
        if category in data:
            # Support both old format (lowercase) and new format (uppercase)
            for old_key, new_key in [
                ("GOOD", "good"),
                ("BAD", "bad"),
                ("UNKWN", "unknown"),
                ("reproducible", "good"),
                ("unreproducible", "bad"),
                ("notfound", "unknown"),
                ("pending", "unknown"),
            ]:
                stats[new_key] += len(data[category].get(old_key, []))

    return stats


class HTMLReportGenerator:
    """Generates HTML reports from rebuild results."""

    def __init__(self, output_dir: Path):
        """Initialize the report generator.

        Args:
            output_dir: Directory to write reports to.
        """
        self.output_dir = output_dir
        self.diffoscope_dir = output_dir / "diffoscope"
        self.artifacts_dir = output_dir / "artifacts"

        # Setup Jinja2 environment
        self.env = Environment(
            loader=PackageLoader("rebuilder.reporting", "templates"),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def _ensure_dirs(self) -> None:
        """Create output directories."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.diffoscope_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def generate_target_page(
        self,
        version: str,
        target: str,
        target_data: dict[str, Any],
        release_dir: str,
    ) -> dict[str, int]:
        """Generate a detailed page for a specific target.

        Args:
            version: OpenWrt version.
            target: Target architecture.
            target_data: Results data for this target.
            release_dir: Release directory name.

        Returns:
            Statistics dictionary for this target.
        """
        target_slug = target.replace("/", "_")
        target_dir = self.output_dir / release_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        stats = calculate_stats(target_data)

        template = self.env.get_template("target.html")
        html = template.render(
            version=version,
            target=target,
            release_dir=release_dir,
            data=target_data,
            stats=stats,
        )

        output_path = target_dir / f"{target_slug}.html"
        output_path.write_text(html)
        logger.info(f"Generated {output_path}")

        return stats

    def generate_release_page(
        self,
        version: str,
        targets_data: dict[str, Any],
        history: VersionHistory | None = None,
    ) -> dict[str, int]:
        """Generate a release overview page.

        Args:
            version: OpenWrt version.
            targets_data: Dictionary of target -> results.
            history: Optional history data for timeline visualization.

        Returns:
            Aggregated statistics for this version.
        """
        release_dir = version.replace(".", "_").replace("/", "_")
        version_stats = {"good": 0, "bad": 0, "unknown": 0}

        # Process each target and collect stats
        targets_with_stats = {}
        for target, target_data in targets_data.items():
            target_stats = self.generate_target_page(version, target, target_data, release_dir)
            targets_with_stats[target] = {
                "data": target_data,
                "stats": target_stats,
            }
            for status in version_stats:
                version_stats[status] += target_stats.get(status, 0)

        # Prepare history data for the chart (JSON-encoded for JavaScript)
        history_json = json.dumps(history) if history else "null"

        # Generate release page
        template = self.env.get_template("release.html")
        html = template.render(
            version=version,
            release_dir=release_dir,
            targets=targets_with_stats,
            version_stats=version_stats,
            history=history,
            history_json=history_json,
        )

        output_path = self.output_dir / f"{release_dir}.html"
        output_path.write_text(html)
        logger.info(f"Generated {output_path}")

        return version_stats

    def generate_index_page(
        self,
        combined_data: dict[str, Any],
        build_info: BuildInfo | None = None,
        all_histories: dict[str, VersionHistory] | None = None,
    ) -> dict[str, int]:
        """Generate the main index page.

        Args:
            combined_data: Dictionary of version -> targets -> results.
            build_info: Optional build metadata.
            all_histories: Optional dict of base_version -> history data.

        Returns:
            Overall statistics.
        """
        overall_stats = {"good": 0, "bad": 0, "unknown": 0}

        if all_histories is None:
            all_histories = {}

        # Group versions by base version for history lookup
        # e.g., "SNAPSHOT/r28532-abc" -> "SNAPSHOT"
        def get_base_version(version_key: str) -> str:
            if "SNAPSHOT" in version_key and "/" in version_key:
                return version_key.split("/", 1)[0]
            return version_key

        # Process each release and collect stats
        releases = {}
        for version, targets_data in combined_data.items():
            base_version = get_base_version(version)
            history = all_histories.get(base_version)

            version_stats = self.generate_release_page(version, targets_data, history)
            releases[version] = {
                "stats": version_stats,
                "target_count": len(targets_data),
                "has_history": history is not None and len(history.get("entries", [])) > 1,
            }
            for status in overall_stats:
                overall_stats[status] += version_stats.get(status, 0)

        # Prepare combined history for index page chart
        all_histories_json = json.dumps(all_histories) if all_histories else "{}"

        # Generate index page
        template = self.env.get_template("index.html")
        html = template.render(
            releases=releases,
            overall_stats=overall_stats,
            build_info=build_info,
            all_histories=all_histories,
            all_histories_json=all_histories_json,
        )

        output_path = self.output_dir / "index.html"
        output_path.write_text(html)
        logger.info(f"Generated {output_path}")

        return overall_stats

    def copy_diffoscope_reports(self, results_dir: Path) -> int:
        """Copy diffoscope HTML reports to the output directory.

        Args:
            results_dir: Directory containing result artifacts.

        Returns:
            Number of files copied.
        """
        count = 0
        for html_file in results_dir.glob("**/*.html"):
            if html_file.name != "index.html":
                dest = self.diffoscope_dir / html_file.name
                shutil.copy2(html_file, dest)
                count += 1
                logger.debug(f"Copied {html_file} to {dest}")

        logger.info(f"Copied {count} diffoscope reports")
        return count

    def copy_unreproducible_artifacts(self, results_dir: Path) -> int:
        """Copy unreproducible artifacts to the output directory.

        Copies stored origin and rebuild files for manual inspection.

        Args:
            results_dir: Directory containing result artifacts.

        Returns:
            Number of artifact pairs copied.
        """
        count = 0
        artifacts_src = results_dir / "artifacts"

        if not artifacts_src.exists():
            logger.debug("No artifacts directory found")
            return 0

        # Copy the entire artifacts directory structure
        for category_dir in artifacts_src.iterdir():
            if not category_dir.is_dir():
                continue

            category_name = category_dir.name
            for artifact_dir in category_dir.iterdir():
                if not artifact_dir.is_dir():
                    continue

                # Create destination directory
                dest_dir = self.artifacts_dir / category_name / artifact_dir.name
                dest_dir.mkdir(parents=True, exist_ok=True)

                # Copy all files in the artifact directory
                for artifact_file in artifact_dir.iterdir():
                    if artifact_file.is_file():
                        dest = dest_dir / artifact_file.name
                        shutil.copy2(artifact_file, dest)
                        logger.debug(f"Copied {artifact_file} to {dest}")

                count += 1

        logger.info(f"Copied {count} unreproducible artifact pairs")
        return count

    def generate_all(
        self,
        combined_data: dict[str, Any],
        results_dir: Path | None = None,
        build_info: BuildInfo | None = None,
        all_histories: dict[str, VersionHistory] | None = None,
    ) -> dict[str, int]:
        """Generate complete HTML report hierarchy.

        Args:
            combined_data: Combined RBVF output data.
            results_dir: Optional directory with diffoscope reports.
            build_info: Optional build metadata.
            all_histories: Optional dict of base_version -> history data.

        Returns:
            Overall statistics.
        """
        self._ensure_dirs()

        if results_dir:
            self.copy_diffoscope_reports(results_dir)
            self.copy_unreproducible_artifacts(results_dir)

        return self.generate_index_page(combined_data, build_info, all_histories)


def generate_reports(
    combined_data: dict[str, Any],
    output_dir: Path,
    results_dir: Path | None = None,
) -> dict[str, int]:
    """Convenience function to generate all reports.

    Args:
        combined_data: Combined RBVF output data.
        output_dir: Directory to write reports to.
        results_dir: Optional directory with diffoscope reports.

    Returns:
        Overall statistics.
    """
    generator = HTMLReportGenerator(output_dir)
    build_info = BuildInfo.from_environment()
    return generator.generate_all(combined_data, results_dir, build_info)
