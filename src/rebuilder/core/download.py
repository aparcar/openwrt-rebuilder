"""File download utilities."""

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Raised when a download fails."""

    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"Failed to download {url}: {reason}")


def download_file(url: str, path: Path | None = None, timeout: int = 30) -> bytes:
    """Download a file from a URL.

    Args:
        url: URL to download from.
        path: Optional path to save the file to.
        timeout: Request timeout in seconds.

    Returns:
        The downloaded content as bytes.

    Raises:
        DownloadError: If the download fails.
    """
    logger.debug(f"Downloading {url}")
    try:
        with urlopen(url, timeout=timeout) as response:
            content = response.read()
    except HTTPError as e:
        raise DownloadError(url, f"HTTP {e.code}: {e.reason}") from e
    except URLError as e:
        raise DownloadError(url, str(e.reason)) from e
    except TimeoutError as e:
        raise DownloadError(url, "Request timed out") from e

    if path:
        logger.debug(f"Saving to {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    return bytes(content)


def download_text(url: str, path: Path | None = None, timeout: int = 30) -> str:
    """Download a text file from a URL.

    Args:
        url: URL to download from.
        path: Optional path to save the file to.
        timeout: Request timeout in seconds.

    Returns:
        The downloaded content as a string.

    Raises:
        DownloadError: If the download fails.
    """
    content = download_file(url, path, timeout)
    return content.decode("utf-8")


def download_json(url: str, timeout: int = 30) -> dict[str, Any]:
    """Download and parse a JSON file from a URL.

    Args:
        url: URL to download from.
        timeout: Request timeout in seconds.

    Returns:
        The parsed JSON data.

    Raises:
        DownloadError: If the download fails.
        json.JSONDecodeError: If the content is not valid JSON.
    """
    content = download_text(url, timeout=timeout)
    result: dict[str, Any] = json.loads(content)
    return result


def discover_kernel_version(origin_url: str, target_dir: str) -> str:
    """Discover the kernel version string from the origin server.

    The kernel version is extracted from the kmods sha256sums file which
    contains paths like: kmods/6.12.63-1-abc123def/kmod-foo.apk

    Args:
        origin_url: Base URL for OpenWrt downloads.
        target_dir: Target directory path (e.g., "snapshots/targets/x86/64").

    Returns:
        The kernel version string (e.g., "6.12.63-1-abc123def"), or empty string if not found.
    """
    # Try to fetch target sha256sums and find the kmods path
    target_url = f"{origin_url}/{target_dir}/sha256sums"
    try:
        content = download_text(target_url)
        # Find all kmods paths and get the one with the highest kernel version
        matches = re.findall(r"kmods/([^/]+)/", content)
        if matches:
            # Get unique versions and sort by version number (descending)
            unique_versions = sorted(set(matches), reverse=True)
            kernel_version = unique_versions[0]
            logger.info(f"Discovered kernel version from origin: {kernel_version}")
            return kernel_version
    except DownloadError:
        logger.debug(f"Could not fetch {target_url}")

    logger.warning("Could not discover kernel version from origin")
    return ""


def build_kmod_path_map(origin_url: str, target_dir: str) -> dict[str, str]:
    """Build a mapping of kmod filenames to their full paths.

    Args:
        origin_url: Base URL for OpenWrt downloads.
        target_dir: Target directory path (e.g., "snapshots/targets/x86/64").

    Returns:
        Dictionary mapping kmod filename to full path (e.g., {"kmod-foo.apk": "kmods/6.12.63-1-abc/kmod-foo.apk"}).
    """
    kmod_map: dict[str, str] = {}
    target_url = f"{origin_url}/{target_dir}/sha256sums"

    try:
        content = download_text(target_url)
        # Parse paths like: *kmods/6.12.63-1-abc123/kmod-foo.apk
        for line in content.splitlines():
            match = re.search(r"\*(kmods/[^/]+/([^/]+\.apk))", line)
            if match:
                full_path = match.group(1)
                filename = match.group(2)
                kmod_map[filename] = full_path
        logger.info(f"Built kmod path map with {len(kmod_map)} entries")
    except DownloadError:
        logger.warning(f"Could not fetch {target_url} for kmod path map")

    return kmod_map
