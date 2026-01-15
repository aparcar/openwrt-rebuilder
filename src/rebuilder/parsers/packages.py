"""Parser for OpenWrt package index files."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PackageIndex:
    """Parsed package index data."""

    architecture: str
    packages: dict[str, str]  # package name -> version

    def get_version_map(self) -> dict[str, tuple[str, str]]:
        """Create a mapping from 'name-version' to (name, version) tuple.

        Returns:
            Dictionary mapping 'package-version' strings to (package, version) tuples.
        """
        return {f"{name}-{version}": (name, version) for name, version in self.packages.items()}


def parse_packages(content: str) -> PackageIndex:
    """Parse package index from JSON content.

    Args:
        content: JSON content of index.json file.

    Returns:
        PackageIndex with architecture and package mappings.
    """
    data = json.loads(content)
    return PackageIndex(
        architecture=data.get("architecture", ""),
        packages=data.get("packages", {}),
    )


def parse_packages_file(path: Path) -> PackageIndex:
    """Parse package index from a file.

    Args:
        path: Path to the index.json file.

    Returns:
        PackageIndex with architecture and package mappings.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    return parse_packages(path.read_text())
