"""JSON output generation in RBVF format."""

import json
from pathlib import Path
from typing import Any

from rebuilder.config import Config
from rebuilder.models import Suite


def write_rbvf_output(config: Config, suite: Suite, output_path: Path | None = None) -> Path:
    """Write results in Reproducible Builds Verification Format (RBVF).

    Args:
        config: Rebuild configuration.
        suite: Suite containing all results.
        output_path: Optional custom output path.

    Returns:
        Path to the written output file.
    """
    if output_path is None:
        output_path = config.results_dir / "output.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {config.version: {config.target: suite.to_dict()}}

    output_path.write_text(json.dumps(data, indent=4))
    return output_path


def load_rbvf_output(path: Path) -> dict[str, Any]:
    """Load RBVF output from a file.

    Args:
        path: Path to the output.json file.

    Returns:
        Parsed JSON data.
    """
    result: dict[str, Any] = json.loads(path.read_text())
    return result


def merge_rbvf_outputs(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple RBVF outputs into one.

    Args:
        outputs: List of RBVF output dictionaries.

    Returns:
        Merged output dictionary.
    """
    merged: dict[str, Any] = {}

    for output in outputs:
        for version, version_data in output.items():
            if version not in merged:
                merged[version] = {}
            merged[version].update(version_data)

    return merged
