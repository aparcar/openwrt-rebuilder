"""Parser for OpenWrt profiles.json files."""

import json
from pathlib import Path


def parse_profiles(content: str) -> dict[str, str]:
    """Parse image checksums from profiles.json content.

    Args:
        content: JSON content of profiles.json file.

    Returns:
        Dictionary mapping image filename to SHA256 hash.
    """
    data = json.loads(content)
    files: dict[str, str] = {}

    for profile in data.get("profiles", {}).values():
        for image in profile.get("images", []):
            name = image.get("name")
            sha256 = image.get("sha256")
            if name and sha256:
                files[name] = sha256

    return files


def parse_profiles_file(path: Path) -> dict[str, str]:
    """Parse image checksums from a profiles.json file.

    Args:
        path: Path to the profiles.json file.

    Returns:
        Dictionary mapping image filename to SHA256 hash.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    return parse_profiles(path.read_text())
