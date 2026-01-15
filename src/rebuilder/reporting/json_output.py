"""JSON output generation in rebuilderd-compatible format for static hosting."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rebuilder.config import Config
from rebuilder.models import Suite


def write_rbvf_output(config: Config, suite: Suite, output_path: Path | None = None) -> Path:
    """Write results in rebuilderd-compatible format.

    Generates a structure suitable for static hosting:
    - packages.json: List of all package results
    - images.json: List of all image results
    - stats.json: Summary statistics

    Args:
        config: Rebuild configuration.
        suite: Suite containing all results.
        output_path: Optional custom output path (for backwards compatibility).

    Returns:
        Path to the output directory.
    """
    output_dir = output_path.parent if output_path else config.results_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Flatten results into lists (rebuilderd style)
    packages = []
    for status_list in [suite.packages.good, suite.packages.bad, suite.packages.unknown]:
        packages.extend([r.to_dict() for r in status_list])

    images = []
    for status_list in [suite.images.good, suite.images.bad, suite.images.unknown]:
        images.extend([r.to_dict() for r in status_list])

    # Write packages.json
    (output_dir / "packages.json").write_text(json.dumps(packages, indent=2))

    # Write images.json
    (output_dir / "images.json").write_text(json.dumps(images, indent=2))

    # Write stats.json (rebuilderd dashboard format)
    pkg_stats = suite.packages.stats()
    img_stats = suite.images.stats()
    stats = {
        "target": config.target,
        "version": config.version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "packages": pkg_stats,
        "images": img_stats,
        "totals": {
            "good": pkg_stats["good"] + img_stats["good"],
            "bad": pkg_stats["bad"] + img_stats["bad"],
            "unknown": pkg_stats["unknown"] + img_stats["unknown"],
        },
    }
    (output_dir / "stats.json").write_text(json.dumps(stats, indent=2))

    return output_dir / "stats.json"


def generate_index(output_dir: Path, all_stats: list[dict[str, Any]]) -> Path:
    """Generate a top-level index.json for all targets.

    Args:
        output_dir: Output directory.
        all_stats: List of stats from each target.

    Returns:
        Path to the index.json file.
    """
    # Aggregate stats
    totals = {"good": 0, "bad": 0, "unknown": 0}
    suites: dict[str, dict[str, Any]] = {}

    for stat in all_stats:
        version = stat.get("version", "unknown")
        if version not in suites:
            suites[version] = {"good": 0, "bad": 0, "unknown": 0, "targets": []}

        suites[version]["targets"].append(stat["target"])
        for key in totals:
            totals[key] += stat["totals"].get(key, 0)
            suites[version][key] += stat["totals"].get(key, 0)

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": totals,
        "suites": suites,
    }

    index_path = output_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2))
    return index_path
