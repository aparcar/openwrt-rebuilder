"""HTML report generation using Jinja2 templates."""

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from os import environ
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

logger = logging.getLogger(__name__)


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


def calculate_stats(data: dict) -> dict[str, int]:
    """Calculate statistics from result data.

    Args:
        data: Dictionary containing packages and/or images results.

    Returns:
        Dictionary with counts for each status.
    """
    stats = {"reproducible": 0, "unreproducible": 0, "notfound": 0, "pending": 0}

    for category in ["packages", "images"]:
        if category in data:
            for status in stats:
                stats[status] += len(data[category].get(status, []))

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

        # Setup Jinja2 environment
        self.env = Environment(
            loader=PackageLoader("rebuilder.reporting", "templates"),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def _ensure_dirs(self) -> None:
        """Create output directories."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.diffoscope_dir.mkdir(parents=True, exist_ok=True)

    def generate_target_page(
        self,
        version: str,
        target: str,
        target_data: dict,
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
        targets_data: dict,
    ) -> dict[str, int]:
        """Generate a release overview page.

        Args:
            version: OpenWrt version.
            targets_data: Dictionary of target -> results.

        Returns:
            Aggregated statistics for this version.
        """
        release_dir = version.replace(".", "_")
        version_stats = {"reproducible": 0, "unreproducible": 0, "notfound": 0, "pending": 0}

        # Process each target and collect stats
        targets_with_stats = {}
        for target, target_data in targets_data.items():
            target_stats = self.generate_target_page(version, target, target_data, release_dir)
            targets_with_stats[target] = {
                "data": target_data,
                "stats": target_stats,
            }
            for status in version_stats:
                version_stats[status] += target_stats[status]

        # Generate release page
        template = self.env.get_template("release.html")
        html = template.render(
            version=version,
            release_dir=release_dir,
            targets=targets_with_stats,
            version_stats=version_stats,
        )

        output_path = self.output_dir / f"{release_dir}.html"
        output_path.write_text(html)
        logger.info(f"Generated {output_path}")

        return version_stats

    def generate_index_page(
        self,
        combined_data: dict,
        build_info: BuildInfo | None = None,
    ) -> dict[str, int]:
        """Generate the main index page.

        Args:
            combined_data: Dictionary of version -> targets -> results.
            build_info: Optional build metadata.

        Returns:
            Overall statistics.
        """
        overall_stats = {"reproducible": 0, "unreproducible": 0, "notfound": 0, "pending": 0}

        # Process each release and collect stats
        releases = {}
        for version, targets_data in combined_data.items():
            version_stats = self.generate_release_page(version, targets_data)
            releases[version] = {
                "stats": version_stats,
                "target_count": len(targets_data),
            }
            for status in overall_stats:
                overall_stats[status] += version_stats[status]

        # Generate index page
        template = self.env.get_template("index.html")
        html = template.render(
            releases=releases,
            overall_stats=overall_stats,
            build_info=build_info,
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

    def generate_all(
        self,
        combined_data: dict,
        results_dir: Path | None = None,
        build_info: BuildInfo | None = None,
    ) -> dict[str, int]:
        """Generate complete HTML report hierarchy.

        Args:
            combined_data: Combined RBVF output data.
            results_dir: Optional directory with diffoscope reports.
            build_info: Optional build metadata.

        Returns:
            Overall statistics.
        """
        self._ensure_dirs()

        if results_dir:
            self.copy_diffoscope_reports(results_dir)

        return self.generate_index_page(combined_data, build_info)


def generate_reports(
    combined_data: dict,
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
