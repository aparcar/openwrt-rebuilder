"""Comparison logic for rebuild verification."""

import logging
from pathlib import Path

from rebuilder.config import Config
from rebuilder.models import Result, Status, Suite
from rebuilder.parsers import parse_packages, parse_profiles

logger = logging.getLogger(__name__)


class Comparator:
    """Compares rebuilt artifacts against origin builds."""

    def __init__(self, config: Config, suite: Suite):
        """Initialize comparator.

        Args:
            config: Rebuild configuration.
            suite: Suite to store results in.
        """
        self.config = config
        self.suite = suite

    def compare_file(
        self,
        filename: str,
        origin_checksum: str,
        rebuild_checksums: dict[str, str],
    ) -> Status:
        """Compare a single file's checksum.

        Args:
            filename: Name of the file to compare.
            origin_checksum: Expected checksum from origin.
            rebuild_checksums: Dictionary of rebuilt file checksums.

        Returns:
            The comparison status.
        """
        if filename not in rebuild_checksums:
            return Status.NOTFOUND

        if origin_checksum != rebuild_checksums[filename]:
            return Status.UNREPRODUCIBLE

        return Status.REPRODUCIBLE

    def compare_profiles(
        self,
        origin_profiles: dict[str, str],
        rebuild_profiles_path: Path,
    ) -> None:
        """Compare image profiles between origin and rebuild.

        Args:
            origin_profiles: Origin image checksums (filename -> sha256).
            rebuild_profiles_path: Path to rebuilt profiles.json.
        """
        rebuild_profiles = parse_profiles(rebuild_profiles_path.read_text())

        for filename, origin_checksum in origin_profiles.items():
            status = self.compare_file(filename, origin_checksum, rebuild_profiles)
            diffoscope = f"{filename}.html" if status == Status.UNREPRODUCIBLE else None

            result = Result(
                name=filename,
                version=self.config.version,
                arch=self.config.target,
                distribution="openwrt",
                status=status,
                diffoscope=diffoscope,
                files={status.value: [f"targets/{self.config.target}/{filename}"]},
            )
            self.suite.add_result("images", result)

    def compare_packages(
        self,
        origin_checksums: dict[str, str],
        rebuild_checksums: dict[str, str],
        index_path: Path,
        file_prefix: str,
    ) -> None:
        """Compare packages between origin and rebuild.

        Args:
            origin_checksums: Origin package checksums.
            rebuild_checksums: Rebuilt package checksums.
            index_path: Path to package index.json.
            file_prefix: Prefix for file paths in results.
        """
        package_index = parse_packages(index_path.read_text())
        version_map = package_index.get_version_map()

        for filename, rebuild_checksum in rebuild_checksums.items():
            if not filename.endswith((".ipk", ".apk")):
                continue

            status = self.compare_file(
                filename, origin_checksums.get(filename, ""), {filename: rebuild_checksum}
            )

            # Handle case where origin doesn't have this file
            if filename not in origin_checksums:
                status = Status.NOTFOUND

            # Parse package name and version from filename
            map_name = filename.rsplit(".", 1)[0]  # Remove .ipk/.apk extension
            if map_name not in version_map:
                logger.debug(f"Package {map_name} not in index, skipping")
                continue

            package_name, version = version_map[map_name]
            diffoscope = f"{filename}.html" if status == Status.UNREPRODUCIBLE else None

            result = Result(
                name=package_name,
                version=version,
                arch=package_index.architecture,
                distribution="openwrt",
                status=status,
                diffoscope=diffoscope,
                files={status.value: [f"{file_prefix}/{filename}"]},
            )
            self.suite.add_result("packages", result)
