#!/usr/bin/env python3
"""
Combine results from multiple rebuild runs and generate HTML reports.

This script collects output.json files from parallel rebuild jobs,
merges them, and generates a hierarchical HTML report structure.

Usage:
    python scripts/combine_results.py [--results-dir RESULTS] [--output-dir OUTPUT]

For backwards compatibility, running without arguments uses:
    - results/ as the input directory
    - combined_results/ as the output directory
"""

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from os import environ
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Try to import from the new package structure
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.rebuilder.reporting.html import BuildInfo, HTMLReportGenerator

    USE_NEW_TEMPLATES = True
except ImportError:
    logger.warning("Could not import new package, using legacy HTML generation")
    USE_NEW_TEMPLATES = False


def collect_results(results_dir: Path) -> tuple[dict, list[Path]]:
    """Collect all output.json files and HTML files from a directory.

    Args:
        results_dir: Directory to search for output.json files.

    Returns:
        Tuple of (combined_data dict, list of HTML file paths).
    """
    combined_data = {}
    html_files = []

    for output_path in results_dir.glob("**/output.json"):
        logger.info(f"Found: {output_path}")
        results_subdir = output_path.parent

        try:
            with open(output_path) as f:
                data = json.load(f)

            # Merge the data
            for version, version_data in data.items():
                if version not in combined_data:
                    combined_data[version] = {}
                combined_data[version].update(version_data)

            # Collect HTML files (diffoscope reports)
            for html_file in results_subdir.glob("**/*.html"):
                if html_file.name != "index.html":
                    html_files.append(html_file)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse {output_path}: {e}")
        except Exception as e:
            logger.error(f"Error reading {output_path}: {e}")

    return combined_data, html_files


def generate_reports_legacy(combined_data: dict, output_dir: Path, html_files: list[Path]) -> dict:
    """Generate HTML reports using legacy inline templates.

    Args:
        combined_data: Merged results data.
        output_dir: Output directory.
        html_files: List of diffoscope HTML files to copy.

    Returns:
        Overall statistics.
    """
    diffoscope_dir = output_dir / "diffoscope"
    diffoscope_dir.mkdir(parents=True, exist_ok=True)

    # Copy diffoscope files
    for html_file in html_files:
        dest = diffoscope_dir / html_file.name
        logger.debug(f"Copying {html_file} to {dest}")
        shutil.copy2(html_file, dest)

    # Build metadata
    build_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    github_sha = environ.get("GITHUB_SHA", "unknown")[:8]
    github_ref = environ.get("GITHUB_REF_NAME", "unknown")

    def calculate_stats(data: dict) -> dict:
        stats = {"reproducible": 0, "unreproducible": 0, "notfound": 0, "pending": 0}
        for category in ["packages", "images"]:
            if category in data:
                for status in stats:
                    stats[status] += len(data[category].get(status, []))
        return stats

    def generate_target_page(version, target, target_data, release_dir):
        target_slug = target.replace("/", "_")
        (output_dir / release_dir).mkdir(parents=True, exist_ok=True)

        target_stats = calculate_stats(target_data)
        total_items = sum(target_stats.values())
        reproducible_percent = (
            (target_stats["reproducible"] / total_items * 100) if total_items > 0 else 0
        )

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{target} - {version} - OpenWrt Reproducible Build Results</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
        .breadcrumb {{ margin-bottom: 20px; }}
        .breadcrumb a {{ color: #3498db; text-decoration: none; }}
        .category {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; margin: 15px 0; }}
        .category-header {{ background: #e9ecef; padding: 15px; font-weight: bold; font-size: 1.2em; }}
        .status-header {{ padding: 10px 15px; font-weight: bold; margin: 10px 0; border-radius: 3px; }}
        .status-header.reproducible {{ background: #d4edda; color: #155724; }}
        .status-header.unreproducible {{ background: #f8d7da; color: #721c24; }}
        .status-header.notfound {{ background: #fff3cd; color: #856404; }}
        .status-header.pending {{ background: #d1ecf1; color: #0c5460; }}
        .item {{ margin: 8px 0; padding: 12px; background: white; border-left: 4px solid #ddd; border-radius: 3px; }}
        .item.reproducible {{ border-left-color: #28a745; }}
        .item.unreproducible {{ border-left-color: #dc3545; }}
        .item.notfound {{ border-left-color: #ffc107; }}
        .item.pending {{ border-left-color: #17a2b8; }}
        .item-name {{ font-weight: bold; margin-bottom: 5px; }}
        .item-details {{ font-size: 0.9em; color: #666; }}
        .diffoscope-link a {{ background: #007bff; color: white; padding: 4px 8px; border-radius: 3px; text-decoration: none; font-size: 0.85em; }}
        .summary-box {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 15px 0; }}
    </style>
</head>
<body>
    <div class="breadcrumb">
        <a href="../index.html">← All Releases</a> /
        <a href="../{release_dir}.html">{version}</a> / {target}
    </div>
    <div class="header"><h1>{target}</h1><h2>Version: {version}</h2></div>
    <div class="summary-box">
        <h3>Target Summary</h3>
        <p><strong>{reproducible_percent:.1f}% Reproducible</strong> ({target_stats["reproducible"]} of {total_items} items)</p>
    </div>
"""
        for category in ["images", "packages"]:
            if category not in target_data:
                continue
            html_content += (
                f'<div class="category"><div class="category-header">{category.title()}</div>'
            )
            for status in ["reproducible", "unreproducible", "notfound", "pending"]:
                items = target_data[category].get(status, [])
                if not items:
                    continue
                html_content += (
                    f'<div class="status-header {status}">{status.title()} ({len(items)})</div>'
                )
                for item in items:
                    html_content += (
                        f'<div class="item {status}"><div class="item-name">{item["name"]}</div>'
                    )
                    html_content += f'<div class="item-details">Arch: {item.get("arch", "N/A")} | Version: {item.get("version", "N/A")}</div>'
                    if item.get("diffoscope"):
                        html_content += f'<div class="diffoscope-link"><a href="../diffoscope/{item["diffoscope"]}" target="_blank">View Diffoscope</a></div>'
                    html_content += "</div>"
            html_content += "</div>"
        html_content += "</body></html>"
        (output_dir / release_dir / f"{target_slug}.html").write_text(html_content)
        return target_stats

    def generate_release_page(version, targets_data):
        release_dir = version.replace(".", "_")
        version_stats = {"reproducible": 0, "unreproducible": 0, "notfound": 0, "pending": 0}

        for target, target_data in targets_data.items():
            target_stats = generate_target_page(version, target, target_data, release_dir)
            for status in version_stats:
                version_stats[status] += target_stats[status]

        total = sum(version_stats.values())
        percent = (version_stats["reproducible"] / total * 100) if total > 0 else 0

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{version} - OpenWrt Reproducible Build Results</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }}
        .breadcrumb {{ margin-bottom: 20px; }}
        .breadcrumb a {{ color: #3498db; text-decoration: none; }}
        .targets-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 20px 0; }}
        .target-card {{ background: white; border: 1px solid #ddd; border-radius: 8px; padding: 20px; }}
        .target-card a {{ color: #2c3e50; text-decoration: none; font-weight: bold; }}
        .progress-bar {{ background: #e0e0e0; border-radius: 10px; height: 12px; margin: 10px 0; }}
        .progress-fill {{ height: 100%; border-radius: 10px; background: linear-gradient(to right, #28a745, #20c997); }}
    </style>
</head>
<body>
    <div class="breadcrumb"><a href="index.html">← All Releases</a></div>
    <div class="header"><h1>OpenWrt {version}</h1><p>{percent:.1f}% Reproducible</p></div>
    <div class="targets-grid">
"""
        for target, target_data in targets_data.items():
            target_slug = target.replace("/", "_")
            t_stats = calculate_stats(target_data)
            t_total = sum(t_stats.values())
            t_percent = (t_stats["reproducible"] / t_total * 100) if t_total > 0 else 0
            html_content += f'''<div class="target-card">
                <a href="{release_dir}/{target_slug}.html">{target}</a>
                <div class="progress-bar"><div class="progress-fill" style="width: {t_percent:.1f}%"></div></div>
                <div style="text-align: center;">{t_percent:.1f}% Reproducible</div>
            </div>'''
        html_content += "</div></body></html>"
        (output_dir / f"{release_dir}.html").write_text(html_content)
        return version_stats

    # Generate pages
    overall_stats = {"reproducible": 0, "unreproducible": 0, "notfound": 0, "pending": 0}
    release_cards = ""

    for version, targets_data in combined_data.items():
        version_stats = generate_release_page(version, targets_data)
        for status in overall_stats:
            overall_stats[status] += version_stats[status]

        total = sum(version_stats.values())
        percent = (version_stats["reproducible"] / total * 100) if total > 0 else 0
        release_file = f"{version.replace('.', '_')}.html"
        release_cards += f'''<div class="release-card">
            <a href="{release_file}">OpenWrt {version}</a>
            <div class="progress-bar"><div class="progress-fill" style="width: {percent:.1f}%"></div></div>
            <div style="text-align: center; font-weight: bold;">{percent:.1f}% Reproducible</div>
            <div style="text-align: center; color: #666;">{len(targets_data)} targets</div>
        </div>'''

    total_all = sum(overall_stats.values())
    overall_percent = (overall_stats["reproducible"] / total_all * 100) if total_all > 0 else 0

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>OpenWrt Reproducible Build Results</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #2c3e50; color: white; padding: 25px; border-radius: 8px; margin-bottom: 30px; }}
        .build-info {{ font-size: 0.9em; margin-top: 15px; opacity: 0.9; }}
        .releases-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 25px; }}
        .release-card {{ background: white; border: 1px solid #ddd; border-radius: 10px; padding: 25px; }}
        .release-card a {{ color: #2c3e50; text-decoration: none; font-size: 1.3em; font-weight: bold; }}
        .progress-bar {{ background: #e0e0e0; border-radius: 12px; height: 16px; margin: 15px 0; }}
        .progress-fill {{ height: 100%; border-radius: 12px; background: linear-gradient(to right, #28a745, #20c997); }}
        .summary {{ background: #e8f4fd; border-radius: 10px; padding: 30px; margin: 40px 0; text-align: center; }}
        .footer {{ margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 8px; font-size: 0.9em; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>OpenWrt Reproducible Build Results</h1>
        <div class="build-info">Build: {build_time} | Commit: {github_sha} | Branch: {github_ref}</div>
    </div>
    <div class="releases-grid">{release_cards}</div>
    <div class="summary">
        <h2>Overall: {overall_percent:.1f}% Reproducible</h2>
        <p>{overall_stats["reproducible"]} of {total_all} items</p>
    </div>
    <div class="footer">
        <p>Generated by OpenWrt Reproducible Build CI | <a href="https://reproducible-builds.org/">Learn more</a></p>
    </div>
</body>
</html>"""
    (output_dir / "index.html").write_text(index_html)
    return overall_stats


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Combine rebuild results and generate HTML reports"
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory containing result artifacts (default: results)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("combined_results"),
        help="Directory to write combined output (default: combined_results)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Force legacy HTML generation (no Jinja2 templates)",
    )

    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Collect results
    logger.info(f"Collecting results from {args.results_dir}")
    combined_data, html_files = collect_results(args.results_dir)

    if not combined_data:
        logger.error(f"No output.json files found in {args.results_dir}")
        return 1

    logger.info(f"Found {len(combined_data)} version(s), {len(html_files)} diffoscope reports")

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Write combined JSON
    combined_json_path = args.output_dir / "output.json"
    combined_json_path.write_text(json.dumps(combined_data, indent=2))
    logger.info(f"Written combined JSON to {combined_json_path}")

    # Generate HTML reports
    logger.info("Generating HTML reports...")

    if USE_NEW_TEMPLATES and not args.legacy:
        # Use new Jinja2-based templates
        generator = HTMLReportGenerator(args.output_dir)
        build_info = BuildInfo.from_environment()
        stats = generator.generate_all(combined_data, args.results_dir, build_info)
    else:
        # Use legacy inline HTML
        stats = generate_reports_legacy(combined_data, args.output_dir, html_files)

    # Print summary
    total = sum(stats.values())
    percent = (stats["reproducible"] / total * 100) if total > 0 else 0

    logger.info("=" * 60)
    logger.info(f"Summary: {percent:.1f}% Reproducible ({stats['reproducible']}/{total})")
    logger.info(f"  Unreproducible: {stats['unreproducible']}")
    logger.info(f"  Not found: {stats['notfound']}")
    logger.info(f"  Pending: {stats['pending']}")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
