"""SDK-based single-package rebuild for the rebuilderd OpenWrt backend.

Rebuilds one published apk package by downloading the matching OpenWrt SDK
tarball, unpacking it, and compiling just that package into an output directory
for rebuilderd to compare. This is the Python port of the old
``worker/rebuilder-openwrt-package.sh``: the build runs DIRECTLY in the worker
container (no nested container, no podman), like the archlinux/debian backends.

The build identity is passed in: the apk filename plus the target/subtarget and
release of the SDK to build it with. The published apk URL only names the
package architecture (``.../packages/<arch>/<feed>/<file>.apk``), which does not
identify a target — several ABI-compatible targets share one arch — so resolving
an arch to a target is the caller's job.
"""

import fcntl
import hashlib
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rebuilder.core.command import CommandRunner
from rebuilder.core.download import DownloadError, download_file, download_text

logger = logging.getLogger(__name__)


class PackageRebuildError(Exception):
    """Raised when a single-package rebuild cannot proceed."""


@dataclass(frozen=True)
class PackageSource:
    """Build identity for a single apk package."""

    target: str  # target/subtarget the SDK is published under, e.g. "x86/64"
    release: str  # "SNAPSHOT" or e.g. "24.10.0" / "24.10-SNAPSHOT"
    name: str

    @property
    def version_path(self) -> str:
        """Path segment on the origin server: snapshots/ or releases/<rel>/."""
        return "snapshots" if self.release == "SNAPSHOT" else f"releases/{self.release}"


def parse_package_name(filename: str) -> str:
    """Split ``<name>-<version>.apk`` into the package name.

    The apk version begins at the first ``-`` followed by a digit. Names that
    themselves contain ``-<digit>`` misparse — an accepted limitation, matching
    the shell backend.
    """
    if not filename.endswith(".apk"):
        raise PackageRebuildError(f"unsupported artifact (expected .apk): {filename}")
    stem = filename[: -len(".apk")]
    match = re.search(r"-\d", stem)
    if not match:
        raise PackageRebuildError(f"could not parse package name from {filename}")
    return stem[: match.start()]


def make_source(package: str, target: str, release: str) -> PackageSource:
    """Build a PackageSource from the caller's parameters.

    ``package`` is the apk filename (``<name>-<version>.apk``); its name is
    parsed out. ``target`` and ``release`` name the SDK to build with and must
    be passed in: an apk carries neither, and the package architecture in its
    URL does not identify a target (several targets share one arch), so mapping
    an arch to a target is the caller's job, not the rebuilder's.
    """
    if "/" not in target:
        raise PackageRebuildError(f"target must be '<target>/<subtarget>', got {target!r}")
    if not release:
        raise PackageRebuildError("release is required")
    return PackageSource(target=target, release=release, name=parse_package_name(package))


@dataclass
class SdkConfig:
    """Locations for the SDK cache and its inputs (all set from CLI parameters)."""

    upstream: str = "https://downloads.openwrt.org"
    sdk_cache: Path = Path.home() / ".cache" / "rebuilderd-openwrt-sdk"
    dl_dir: Path = Path.home() / ".cache" / "rebuilderd-openwrt-dl"
    keyring_dir: Path = Path("/usr/local/share/rebuilderd/openwrt-keys")
    tmpdir: Path = Path("/tmp")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SdkCache:
    """Resolves, GPG-verifies and caches the current SDK tarball per (target, release).

    Always verifies the *current* sha256sums and re-downloads only when the SDK
    changed: an immutable release is a cache hit after the first build, while the
    moving SNAPSHOT automatically picks up each new SDK.
    """

    def __init__(self, config: SdkConfig):
        self.config = config
        config.sdk_cache.mkdir(parents=True, exist_ok=True)
        config.dl_dir.mkdir(parents=True, exist_ok=True)

    def resolve(self, source: PackageSource) -> tuple[Path, str]:
        """Resolve the SDK published for this source's target.

        Returns ``(tarball, base_url)``; the base_url is reused to pin feeds
        from the same target.
        """
        # Lock per (target, release): workers share the SDK cache, so this
        # serializes the verify + first-time download. Held only for that; the
        # unpack/build is lock-free. The lock auto-releases when the fd closes.
        lock_name = f".{source.target}-{source.release}.lock".replace("/", "_")
        lock_path = self.config.sdk_cache / lock_name
        with lock_path.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self._resolve_locked(source)

    def _resolve_locked(self, source: PackageSource) -> tuple[Path, str]:
        base = f"{self.config.upstream}/{source.version_path}/targets/{source.target}"
        try:
            current = self._current_sdk(base)
        except DownloadError as err:  # target dir not published for this release
            raise PackageRebuildError(f"no target published at {base}: {err}") from err
        if current is None:  # published, but ships no SDK tarball
            raise PackageRebuildError(f"no SDK tarball published at {base}")

        sha, name = current
        sdk_dir = self.config.sdk_cache / f"{source.target}-{source.release}".replace("/", "_")
        sdk_dir.mkdir(parents=True, exist_ok=True)
        return self._download_cached(sdk_dir, base, sha, name), base

    def _download_cached(self, sdk_dir: Path, base: str, sha: str, name: str) -> Path:
        tarball = sdk_dir / name
        marker = sdk_dir / ".sha256"

        if tarball.is_file() and marker.exists() and marker.read_text().strip() == sha:
            logger.info("sdk: %s (cached)", tarball)
            return tarball

        logger.info("fetching SDK %s", name)
        for stale in sdk_dir.glob("*.tar.*"):
            stale.unlink()
        marker.unlink(missing_ok=True)
        download_file(f"{base}/{name}", tarball)
        actual = _sha256_file(tarball)
        if actual != sha:
            tarball.unlink(missing_ok=True)
            raise PackageRebuildError(
                f"SDK checksum mismatch for {name}: expected {sha}, got {actual}"
            )
        marker.write_text(f"{sha}\n")
        logger.info("sdk: %s", tarball)
        return tarball

    def _current_sdk(self, base: str) -> tuple[str, str] | None:
        """GPG-verify the current sha256sums and return the SDK (sha, filename).

        Returns ``None`` when the target is published but lists no SDK tarball.
        Raises ``DownloadError`` when the target isn't published at all.
        """
        meta = Path(tempfile.mkdtemp(prefix="rebuilderd-openwrt-sdkmeta.", dir=self.config.tmpdir))
        try:
            sums = meta / "sha256sums"
            asc = meta / "sha256sums.asc"
            sums.write_text(download_text(f"{base}/sha256sums"))
            asc.write_bytes(download_file(f"{base}/sha256sums.asc"))
            self._gpg_verify(meta, asc, sums)

            for line in sums.read_text().splitlines():
                if re.search(r"openwrt-sdk-\S+\.tar\.(xz|zst)", line):
                    # sha256sums format: "<hash> *<filename>"
                    parts = line.split()
                    return parts[0], parts[-1].lstrip("*")
            return None
        finally:
            shutil.rmtree(meta, ignore_errors=True)

    def _gpg_verify(self, workdir: Path, asc: Path, sums: Path) -> None:
        keys = sorted(self.config.keyring_dir.glob("*.asc"))
        if not keys:
            raise PackageRebuildError(f"no OpenWrt keys in {self.config.keyring_dir}")
        gnupghome = workdir / "gnupg"
        gnupghome.mkdir(mode=0o700)
        env = {"GNUPGHOME": str(gnupghome)}
        runner = CommandRunner(cwd=workdir, env=env)
        runner.run(["gpg", "--batch", "--quiet", "--import", *map(str, keys)], capture=True)
        runner.run(["gpg", "--batch", "--verify", str(asc), str(sums)], capture=True)


class PackageRebuilder:
    """Rebuilds a single apk package from the SDK into an output directory."""

    def __init__(self, config: SdkConfig | None = None):
        self.config = config or SdkConfig()
        self.cache = SdkCache(self.config)

    def rebuild(self, package: str, target: str, release: str, output_dir: Path) -> Path | None:
        """Rebuild the apk ``package`` (its filename) with the ``target``/``release`` SDK.

        Returns the path to the rebuilt apk, or ``None`` when the build succeeded
        but the expected artifact did not materialise (so rebuilderd records BAD,
        not a hard failure).
        """
        source = make_source(package, target, release)

        logger.info("=== openwrt package rebuild ===")
        logger.info("file:    %s", package)
        logger.info("target:  %s", source.target)
        logger.info("release: %s", source.release)
        logger.info("package: %s", source.name)

        tarball, base = self.cache.resolve(source)

        work = Path(tempfile.mkdtemp(prefix="rebuilderd-openwrt-sdk.", dir=self.config.tmpdir))
        try:
            self._unpack(tarball, work)
            self._pin_feeds(work, base)
            self._build(work, source)
            return self._collect(work, package, output_dir)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _unpack(self, tarball: Path, work: Path) -> None:
        CommandRunner().run(
            ["tar", "--strip-components=1", "--no-same-owner", "-xf", str(tarball), "-C", str(work)]
        )

    def _pin_feeds(self, work: Path, base: str) -> None:
        # The SDK ships a feeds.conf.default that can drift from the feeds the
        # packages were actually built with. Pin to the exact commits published
        # alongside the target (feeds.buildinfo omits `base`, which the SDK
        # provides) by dropping it in as feeds.conf.
        feeds = download_text(f"{base}/feeds.buildinfo")
        (work / "feeds.conf").write_text(feeds)

    def _build(self, work: Path, source: PackageSource) -> None:
        runner = CommandRunner(cwd=work)
        runner.run(["./scripts/feeds", "update", "-a"], capture=True)
        runner.run(["./scripts/feeds", "install", "-a"], capture=True)
        runner.run(["make", "defconfig"], capture=True)
        runner.run(["./scripts/feeds", "install", source.name], capture=True)

        src = self._source_package(work, source.name)
        logger.info("source:  %s", src)

        # CONFIG_SIGNED_PACKAGES= / CONFIG_SIGN_EACH_PACKAGE= mirror the official
        # package buildbot: published apks carry no build signature, so the
        # rebuild must omit it too or every apk would differ by a signature we
        # can't reproduce.
        dl = f"DL_DIR={self.config.dl_dir}"
        runner.run(["make", dl, f"package/{src}/clean", "V=s"])
        runner.run(
            [
                "make",
                dl,
                f"package/{src}/compile",
                "V=s",
                f"-j{os.cpu_count() or 1}",
                "CONFIG_SIGNED_PACKAGES=",
                "CONFIG_SIGN_EACH_PACKAGE=",
            ]
        )

    def _source_package(self, work: Path, binpkg: str) -> str:
        """Map a binary package to its source package via tmp/.packageinfo.

        index.json names binary packages, which may be subpackages of a source
        (e.g. ruby-tmpdir from package/ruby). Falls back to the binary name.
        """
        packageinfo = work / "tmp" / ".packageinfo"
        if packageinfo.exists():
            src = ""
            for line in packageinfo.read_text().splitlines():
                if line.startswith("Source-Makefile:"):
                    parts = line.split(":", 1)[1].split("/")
                    src = parts[-2] if len(parts) >= 2 else ""
                elif line.startswith("Package:") and line.split(":", 1)[1].strip() == binpkg:
                    if src:
                        return src
        return binpkg

    def _collect(self, work: Path, filename: str, output_dir: Path) -> Path | None:
        for candidate in (work / "bin").rglob(filename):
            if candidate.is_file():
                output_dir.mkdir(parents=True, exist_ok=True)
                dest = output_dir / filename
                shutil.copy(candidate, dest)
                logger.info("wrote %s", dest)
                return dest
        # Build succeeded but the expected apk didn't appear: leave the output
        # empty so rebuilderd records BAD (nothing to compare) rather than FAIL.
        logger.warning("no rebuilt artifact named %s under %s/bin", filename, work)
        for produced in (work / "bin").rglob("*.apk"):
            logger.warning("produced: %s", produced)
        return None
