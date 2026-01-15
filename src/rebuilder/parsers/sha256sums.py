"""Parser for SHA256 checksum files."""

import re
from pathlib import Path


def parse_sha256sums(content: str) -> dict[str, str]:
    """Parse SHA256 checksums from OpenWrt sha256sums file format.

    Args:
        content: Content of the sha256sums file.

    Returns:
        Dictionary mapping filename to SHA256 hash.

    Example:
        >>> content = "abc123 *packages/foo.ipk\\ndef456 *packages/bar.ipk\\n"
        >>> parse_sha256sums(content)
        {'foo.ipk': 'abc123', 'bar.ipk': 'def456'}
    """
    # Pattern: hash followed by " *" and path, extract just the filename
    pattern = r"([a-f0-9]{64}) \*(?:.*/)?(.+)"
    return {filename: checksum for checksum, filename in re.findall(pattern, content)}


def parse_sha256sums_file(path: Path) -> dict[str, str]:
    """Parse SHA256 checksums from a file.

    Args:
        path: Path to the sha256sums file.

    Returns:
        Dictionary mapping filename to SHA256 hash.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    return parse_sha256sums(path.read_text())
