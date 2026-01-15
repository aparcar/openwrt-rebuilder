"""File download utilities."""

import json
import logging
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
