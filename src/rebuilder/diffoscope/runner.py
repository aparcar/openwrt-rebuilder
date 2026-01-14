"""Diffoscope execution via container."""

import logging
import os
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Callable

from rebuilder.config import Config
from rebuilder.core.command import run_command
from rebuilder.core.download import DownloadError, download_file
from rebuilder.models import Result

logger = logging.getLogger(__name__)

# Default container image for diffoscope
DIFFOSCOPE_IMAGE = "registry.salsa.debian.org/reproducible-builds/diffoscope"


class DiffoscopeRunner:
    """Runs diffoscope comparisons on unreproducible builds."""

    def __init__(
        self,
        config: Config,
        container_runtime: str = "podman",
        image: str = DIFFOSCOPE_IMAGE,
        timeout: int = 180,
    ):
        """Initialize diffoscope runner.

        Args:
            config: Rebuild configuration.
            container_runtime: Container runtime to use (podman or docker).
            image: Diffoscope container image.
            timeout: Timeout for diffoscope execution in seconds.
        """
        self.config = config
        self.container_runtime = container_runtime
        self.image = image
        self.timeout = timeout

    def _get_download_url(self, result: Result) -> str:
        """Get the download URL for an origin file."""
        file_path = result.files.get("unreproducible", [""])[0]
        url = f"{self.config.origin_url}/{self.config.release_dir}/{file_path}"

        # Handle kernel module paths
        if "kmod" in url:
            # TODO: Need kernel version to construct proper URL
            url = url.replace("packages", "kmods/KERNEL_VERSION")

        return url

    def _unpack_apk(self, apk_path: Path, unpack_dir: Path, apk_bin: Path) -> None:
        """Unpack an APK file for comparison.

        Args:
            apk_path: Path to the APK file.
            unpack_dir: Directory to unpack into.
            apk_bin: Path to the apk binary.
        """
        unpack_dir.mkdir(parents=True, exist_ok=True)

        # Extract APK contents
        run_command(
            [
                str(apk_bin),
                "--allow-untrusted",
                "extract",
                "--destination",
                str(unpack_dir),
                str(apk_path),
            ],
            ignore_errors=True,
        )

        # Extract metadata
        metadata_yaml = unpack_dir / "metadata.yaml"
        run_command(
            f"{apk_bin} adbdump {apk_path} > {metadata_yaml}",
            shell=True,
            ignore_errors=True,
        )

        # Set deterministic timestamps
        deterministic_ts = 1700000000
        self._set_deterministic_mtime(unpack_dir, deterministic_ts)

    def _set_deterministic_mtime(self, path: Path, timestamp: int) -> None:
        """Set deterministic modification times on all files."""
        for p in path.rglob("*"):
            try:
                os.utime(p, (timestamp, timestamp))
            except OSError:
                pass
        os.utime(path, (timestamp, timestamp))

    def run_single(self, result: Result) -> bool:
        """Run diffoscope on a single unreproducible result.

        Args:
            result: The unreproducible result to analyze.

        Returns:
            True if diffoscope ran successfully.
        """
        if not result.diffoscope:
            logger.warning(f"No diffoscope output path for {result.name}")
            return False

        file_path = result.files.get("unreproducible", [""])[0]
        if not file_path:
            logger.warning(f"No file path for {result.name}")
            return False

        rebuild_file = self.config.bin_path / file_path
        origin_file = rebuild_file.parent / (rebuild_file.name + ".orig")
        results_file = self.config.results_dir / result.diffoscope

        logger.info(f"Running diffoscope on {result.name}")

        # Create output file
        results_file.parent.mkdir(parents=True, exist_ok=True)
        results_file.touch()
        results_file.chmod(0o777)

        # Download origin file
        download_url = self._get_download_url(result)
        try:
            download_file(download_url, origin_file)
        except DownloadError as e:
            logger.error(f"Failed to download {download_url}: {e}")
            return False

        if not rebuild_file.is_file():
            logger.error(f"Rebuild file not found: {rebuild_file}")
            return False

        # Handle APK unpacking
        compare_origin = origin_file
        compare_rebuild = rebuild_file

        if rebuild_file.suffix == ".apk":
            apk_bin = self.config.rebuild_dir / "staging_dir" / "host" / "bin" / "apk"
            if apk_bin.exists():
                origin_unpack = origin_file.with_suffix(".dir")
                rebuild_unpack = rebuild_file.with_suffix(".dir")
                self._unpack_apk(origin_file, origin_unpack, apk_bin)
                self._unpack_apk(rebuild_file, rebuild_unpack, apk_bin)
                compare_origin = origin_unpack
                compare_rebuild = rebuild_unpack

        # Run diffoscope in container
        try:
            cmd = " ".join([
                self.container_runtime,
                "run",
                "--rm",
                "-t",
                "-w", str(self.config.results_dir),
                "-v", f"{compare_origin}:{compare_origin}:ro",
                "-v", f"{compare_rebuild}:{compare_rebuild}:ro",
                "-v", f"{results_file}:{results_file}:rw",
                self.image,
                str(compare_origin.resolve()),
                str(compare_rebuild.resolve()),
                "--html", str(results_file),
            ])
            run_command(cmd, shell=True, ignore_errors=True, timeout=self.timeout)
        except TimeoutError:
            logger.warning(f"Diffoscope timed out for {result.name}")
        except Exception as e:
            logger.error(f"Diffoscope failed for {result.name}: {e}")
            return False

        results_file.chmod(0o755)
        return True

    def run_parallel(self, results: list[Result], workers: int | None = None) -> None:
        """Run diffoscope on multiple results in parallel.

        Args:
            results: List of unreproducible results to analyze.
            workers: Number of parallel workers (default: CPU count).
        """
        if not results:
            logger.info("No unreproducible results to analyze")
            return

        self.config.results_dir.mkdir(parents=True, exist_ok=True)
        num_workers = workers or cpu_count()

        logger.info(f"Running diffoscope on {len(results)} files with {num_workers} workers")

        with Pool(processes=num_workers) as pool:
            pool.map(self.run_single, results)
