#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright © 2022 - 2025 Paul Spooren <mail@aparcar.org>
#
# Based on the reproducible_openwrt.sh
#   © 2014-2019 Holger Levsen <holger@layer-acht.org>
#   © 2015 Reiner Herrmann <reiner@reiner-h.de>
#   © 2016-2018 Alexander Couzens <lynxis@fe80.eu>
#
# Released under the GPLv2

import json
import re
from dataclasses import asdict, dataclass, field
from multiprocessing import Pool, cpu_count
from os import environ, symlink
from pathlib import Path
from subprocess import run
from urllib.request import urlopen
import os


@dataclass
class Result:
    name: str
    version: str
    arch: str
    distribution: str
    status: str
    metadata: dict = field(default_factory=dict)
    log: str = None
    epoch: int = 0
    diffoscope: str = None
    files: dict = field(default_factory=dict)


@dataclass
class Results:
    reproducible: list[Result] = field(default_factory=list)
    pending: list[Result] = field(default_factory=list)
    unreproducible: list[Result] = field(default_factory=list)
    notfound: list[Result] = field(default_factory=list)


@dataclass
class Suite:
    packages: Results = field(default_factory=Results)
    images: Results = field(default_factory=Results)


suite = Suite()


# target to be build
target = environ.get("TARGET", "x86/64").replace("-", "/")

# version to be build
rebuild_version = environ.get("VERSION", "SNAPSHOT")

# where to build OpenWrt
rebuild_path = Path(environ.get("REBUILD_DIR", Path.cwd() / "build" / rebuild_version))

bin_path = rebuild_path / "bin/"

dl_path = Path(environ.get("DL_PATH", rebuild_path / "dl"))

# where to find the origin builds
origin_url = environ.get("ORIGIN_URL", "https://downloads.openwrt.org")

# where to get the openwrt source git
openwrt_git = environ.get("OPENWRT_GIT", "https://github.com/openwrt/openwrt.git")

use_diffoscope = environ.get("USE_DIFFOSCOPE", True)

# number of cores to use
j = environ.get("j", cpu_count() + 1)

# where to store rendered html and diffoscope output
results_path = Path(
    environ.get("RESULTS_DIR", Path.cwd() / "results" / rebuild_version / target)
)


if rebuild_version == "SNAPSHOT":
    print("Using snapshots/")
    release_dir = "snapshots"
    target_dir = f"{release_dir}/targets/{target}"
    branch = "master"
else:
    print(f"Using releases/{rebuild_version}/")
    release_dir = f"releases/{rebuild_version}"
    target_dir = f"{release_dir}/targets/{target}"
    branch = f"openwrt-{rebuild_version.rsplit('.', maxsplit=1)[0]}"

print("Testing for")
print(f"Target {target}")
print(f"Branch {branch}")


def run_command(
    cmd,
    cwd=".",
    ignore_errors=False,
    capture=False,
    env={},
    timeout=None,
    shell=False,
    input_data=None,
):
    """
    Run a command in shell
    """
    print(f"Running {cmd} in {cwd}")
    current_env = environ.copy()
    current_env.update(env)
    proc = run(
        cmd,
        cwd=cwd,
        capture_output=capture,
        text=True,
        env=current_env,
        timeout=timeout,
        shell=shell,
        input=input_data,
        umask=0o22,
    )

    if proc.returncode and not ignore_errors:
        print(f"Error running {cmd}")
        quit(proc.returncode)

    if capture:
        print(proc.stderr)
        return proc.stdout

    return proc


# return content of online file or stores it locally if path is given
def get_file(url, path=None, json_content=False):
    print(f"Downloading {url}")
    try:
        content = urlopen(url).read()
    except Exception as e:
        print(e)
        return 1

    if path:
        print(f"Storing to {path}")
        Path(path).write_bytes(content)
        return 0

    else:
        if json_content:
            return json.loads(content.decode())
        else:
            return content.decode()


# parse the origin sha256sums file from openwrt
def parse_sha256sums(path: Path):
    print(path)
    return {v: k for k, v in re.findall(r"(.+?) \*(?:.*/)?(.+?)\n", path.read_text())}


def parse_origin_sha256sums():
    get_file(
        f"{origin_url}/{target_dir}/sha256sums",
        rebuild_path / "sha256sums_origin",
    )
    return parse_sha256sums(rebuild_path / "sha256sums_origin")


def parse_package_sha256sums(architecture):
    get_file(
        f"{origin_url}/{release_dir}/packages/{architecture}/sha256sums",
        rebuild_path / "sha256sums_packages",
    )
    return parse_sha256sums(rebuild_path / "sha256sums_packages")


def clone_git():
    # initial clone of openwrt.git
    if not rebuild_path.is_dir():
        print(f"Cloning {openwrt_git} to {rebuild_path}")
        run_command(["git", "clone", openwrt_git, rebuild_path])
    else:
        # this is only for local testing
        print("Update existing repository")
        run_command(["git", "fetch", "--all"], rebuild_path)
        run_command(["git", "reset", "--hard", f"origin/{branch}"], rebuild_path)


def setup_config_buildinfo():
    # download buildinfo files
    config_content = get_file(f"{origin_url}/{target_dir}/config.buildinfo")

    # don't build imagebuilder or sdk to save some time
    (rebuild_path / ".config").write_text(
        config_content
        + """CONFIG_COLLECT_KERNEL_DEBUG=n
CONFIG_IB=n
CONFIG_SDK=n
CONFIG_BPF_TOOLCHAIN_HOST=y
CONFIG_MAKE_TOOLCHAIN=n"""
    )
    make("defconfig")


def setup_feeds_buildinfo():
    # download origin buildinfo file containing the feeds
    feeds = get_file(
        f"{origin_url}/{target_dir}/feeds.buildinfo",
    )
    (rebuild_path / "feeds.conf").write_text(feeds)
    print(feeds)


def setup_version_buildinfo():
    global commit_string
    global commit
    # get current commit_string to show in website banner
    commit_string = get_file(f"{origin_url}/{target_dir}/version.buildinfo")[:-1]
    print(f"Remote getver.sh: {commit_string}")
    # ... and parse the actual commit to checkout
    commit = commit_string.split("-")[1]


def setup_kernelmagic():
    global kernelversion

    kernelversion = "-".join(
        run_command(
            [
                "make",
                "--no-print-directory",
                "-C",
                "target/linux/",
                "val.LINUX_VERSION",
                "val.LINUX_RELEASE",
                "val.LINUX_VERMAGIC",
            ],
            rebuild_path,
            capture=True,
            env={"TOPDIR": rebuild_path, "INCLUDE_DIR": rebuild_path / "include"},
        ).splitlines()
    )


def checkout_commit():
    """Checkout the desired commit"""
    global commit
    print(f"Checking out {branch}")
    run_command(["git", "checkout", branch], rebuild_path)
    run_command(["git", "reset", "--hard", commit], rebuild_path)

    if rebuild_version != "SNAPSHOT":
        run_command(
            ["git", "branch", "-f", "-D", f"v{rebuild_version}"],
            rebuild_path,
            ignore_errors=True,
        )
        run_command(
            [
                "git",
                "checkout",
                f"v{rebuild_version}",
                "-f",
                "-b",
                f"v{rebuild_version}",
            ],
            rebuild_path,
        )

    local_getver = run_command(
        ["bash", "./scripts/getver.sh"], rebuild_path, capture=True
    )
    print(f"Local getver.sh: {local_getver}")


def update_feeds():
    """Update the package feeds"""

    run_command(["./scripts/feeds", "update"], rebuild_path)
    run_command(["./scripts/feeds", "install", "-a"], rebuild_path)


def apply_patches():
    """Apply patches for the current rebuild version"""

    patches_dir = Path.cwd() / "patches" / rebuild_version
    if not patches_dir.exists():
        print(f"No patches directory found for version {rebuild_version}")
        return

    patch_files = sorted(patches_dir.glob("*.patch"))
    if not patch_files:
        print(f"No patches found in {patches_dir}")
        return

    print(f"Applying {len(patch_files)} patches for version {rebuild_version}")

    for patch_file in patch_files:
        print(f"Applying patch: {patch_file.name}")
        try:
            # Try applying with -p1 first (most common)
            result = run_command(
                ["git", "apply", patch_file],
                cwd=rebuild_path,
                ignore_errors=False,
            )

            if result.returncode == 0:
                print(f"  Successfully applied {patch_file.name}")
            else:
                print(f"  Failed to apply {patch_file.name}")
                print(f"  Error: {result.stderr}")

        except Exception as e:
            print(f"  Error applying {patch_file.name}: {e}")


def make(*cmd, j=j):
    """Convinience function to run make

    Autoamtically run multithreaded and creates logs
    """

    run_command(
        [
            "make",
            "IGNORE_ERRORS='n m'",
            "BUILD_LOG=1",
            f"BUILD_LOG_DIR={results_path}/logs",
            f"-j{j}",
        ]
        + list(cmd),
        rebuild_path,
    )


def parse_packages(packages_str):
    return json.loads(packages_str)


def parse_profiles(profiles_uri):
    if not isinstance(profiles_uri, Path):
        profiles = get_file(
            f"{origin_url}/{target_dir}/profiles.json", json_content=True
        )
    else:
        profiles = json.loads(profiles_uri.read_text())

    files = {}

    for _, profile in profiles["profiles"].items():
        for image in profile["images"]:
            files[image["name"]] = image["sha256"]

    return files


def compare_profiles(profiles_origin):
    profiles_rebuild = parse_profiles(bin_path / "targets" / target / "profiles.json")

    for filename_origin, checksum_origin in profiles_origin.items():
        name = filename_origin
        diffoscope = None
        if filename_origin not in profiles_rebuild:
            status = "notfound"
        elif checksum_origin != profiles_rebuild[filename_origin]:
            status = "unreproducible"
            diffoscope = f"{filename_origin}.html"
        else:
            status = "reproducible"

        getattr(getattr(suite, "images"), status).append(
            Result(
                name=name,
                version=commit,
                arch=target,
                distribution="openwrt",
                status=status,
                diffoscope=diffoscope,
                log=None,
                files={status: [f"targets/{target}/{filename_origin}"]},
            )
        )


def compare_packages_target():
    package_version_map = {}
    rebuild_packages = parse_packages(
        (bin_path / "targets" / target / "packages" / "index.json").read_text()
    )

    for package, version in rebuild_packages["packages"].items():
        package_version_map[f"{package}-{version}"] = (package, version)

    print(package_version_map)

    rebuild_sums = parse_sha256sums(bin_path / "targets" / target / "sha256sums")
    origin_sums = parse_origin_sha256sums()

    print(origin_sums)

    for filename_rebuild, checksum_origin in rebuild_sums.items():
        diffoscope = None

        if filename_rebuild.endswith((".ipk", ".apk")):
            if filename_rebuild not in origin_sums:
                status = "notfound"
            elif checksum_origin != origin_sums[filename_rebuild]:
                status = "unreproducible"
                diffoscope = f"{filename_rebuild}.html"
            else:
                status = "reproducible"

            map_name = filename_rebuild.rstrip(".ipk").rstrip(".apk")
            if not map_name in package_version_map:
                print(map_name)
                continue
            package, version = package_version_map[map_name]

            getattr(getattr(suite, "packages"), status).append(
                Result(
                    name=package,
                    version=version,
                    arch=rebuild_packages["architecture"],
                    distribution="openwrt",
                    status=status,
                    diffoscope=diffoscope,
                    # log=f"logs/package/{data_origin['Section']}/{data_origin['Package']}/{'compile.txt'}", # TODO
                    files={status: [f"targets/{target}/packages/{filename_rebuild}"]},
                )
            )


def compare_packages_base():
    package_version_map = {}
    architecture = parse_packages(
        (bin_path / "targets" / target / "packages" / "index.json").read_text()
    )["architecture"]

    rebuild_packages = parse_packages(
        (bin_path / "packages" / architecture / "base" / "index.json").read_text()
    )

    for package, version in rebuild_packages["packages"].items():
        package_version_map[f"{package}-{version}"] = (package, version)

    print(package_version_map)

    rebuild_sums = parse_sha256sums(bin_path / "packages" / architecture / "sha256sums")
    origin_sums = parse_package_sha256sums(architecture)

    for filename_rebuild, checksum_origin in rebuild_sums.items():
        diffoscope = None

        if filename_rebuild.endswith((".ipk", ".apk")):
            if filename_rebuild not in origin_sums:
                status = "notfound"
            elif checksum_origin != origin_sums[filename_rebuild]:
                status = "unreproducible"
                diffoscope = f"{filename_rebuild}.html"
            else:
                status = "reproducible"

            map_name = filename_rebuild.split("/")[-1].rstrip(".ipk").rstrip(".apk")
            if not map_name in package_version_map:
                # print(map_name)
                continue
            package, version = package_version_map[map_name]

            getattr(getattr(suite, "packages"), status).append(
                Result(
                    name=package,
                    version=version,
                    arch=rebuild_packages["architecture"],
                    distribution="openwrt",
                    status=status,
                    diffoscope=diffoscope,
                    # log=f"logs/package/{data_origin['Section']}/{data_origin['Package']}/{'compile.txt'}", # TODO
                    files={
                        status: [f"packages/{architecture}/base/{filename_rebuild}"]
                    },
                )
            )


def make_download():
    if rebuild_path / "dl" != dl_path and not dl_path.exists():
        print(f"Symlink {rebuild_path / 'dl'} -> {dl_path.absolute()}")
        symlink(
            dl_path.absolute(),
            rebuild_path / "dl",
        )

    make("download")


def diffoscope(result):
    """
    Download file from openwrt server and compare it, store in output_path
    """
    print(result.files["unreproducible"][0])
    rebuild_file = bin_path / result.files["unreproducible"][0]
    origin_file = rebuild_file.parent / (rebuild_file.name + ".orig")
    results_file = results_path / result.diffoscope
    print(results_file)
    results_file.touch()
    results_file.chmod(0o0777)

    download_url = f"{origin_url}/{release_dir}/{result.files['unreproducible'][0]}"
    if "kmod" in download_url:
        download_url = download_url.replace("packages", f"kmods/{kernelversion}")
    print(download_url)
    if not rebuild_file.is_file():
        print(f"Not found: {rebuild_file}")
        return

    if get_file(download_url, str(origin_file)):
        print(f"Error downloading {download_url}")
        return

    if rebuild_file.suffix == ".apk":
        print("bingo")
        origin_unpack_dir = origin_file.with_suffix(".dir")
        rebuild_unpack_dir = rebuild_file.with_suffix(".dir")
        origin_unpack_dir.mkdir(parents=True, exist_ok=True)
        rebuild_unpack_dir.mkdir(parents=True, exist_ok=True)

        # Unpack origin_file and rebuild_file using apk
        apk_bin = rebuild_path / "staging_dir" / "host" / "bin" / "apk"

        # Extract origin_file
        run_command(
            [
                str(apk_bin),
                "--allow-untrusted",
                "extract",
                "--destination",
                str(origin_unpack_dir),
                str(origin_file),
            ],
            ignore_errors=True,
        )

        # Extract rebuild_file
        run_command(
            [
                str(apk_bin),
                "--allow-untrusted",
                "extract",
                "--destination",
                str(rebuild_unpack_dir),
                str(rebuild_file),
            ],
            ignore_errors=True,
        )

        # Extract metadata from origin_file
        metadata_yaml = origin_unpack_dir / "metadata.yaml"
        run_command(
            f"{apk_bin} adbdump {str(origin_file)} > {metadata_yaml}",
            shell=True,
            ignore_errors=True,
        )

        # Extract metadata from rebuild_file
        metadata_yaml = rebuild_unpack_dir / "metadata.yaml"
        run_command(
            f"{apk_bin} adbdump {str(rebuild_file)} > {metadata_yaml}",
            shell=True,
            ignore_errors=True,
        )

        deterministic_ts = 1700000000  # Example fixed timestamp (seconds since epoch)

        def set_deterministic_mtime(path, ts):
            for p in path.rglob("*"):
                try:
                    os.utime(p, (ts, ts))
                except Exception:
                    pass
            os.utime(path, (ts, ts))

        set_deterministic_mtime(origin_unpack_dir, deterministic_ts)
        set_deterministic_mtime(rebuild_unpack_dir, deterministic_ts)

        origin_file = origin_unpack_dir
        rebuild_file = rebuild_unpack_dir

    try:
        run_command(
            " ".join(
                [
                    "podman",
                    "run",
                    "--rm",
                    "-t",
                    "-w",
                    str(results_path),
                    "-v",
                    f"{origin_file}:{origin_file}:ro",
                    "-v",
                    f"{rebuild_file}:{rebuild_file}:ro",
                    "-v",
                    f"{results_file}:{results_file}:rw",
                    "registry.salsa.debian.org/reproducible-builds/diffoscope",
                    str(origin_file.resolve()),
                    str(rebuild_file.resolve()),
                    "--html",
                    str(results_file),
                ]
            ),
            ignore_errors=True,
            timeout=180,
            shell=True,
        )
    except Exception as e:
        print(
            f"Diffoscope failed on comparing {result.files['unreproducible'][0]} with {e}"
        )
    results_file.chmod(0o0755)


def get_arch():
    return run_command(
        ["make", "--no-print-directory", "val.ARCH_PACKAGES"],
        rebuild_path,
        capture=True,
        env={"TOPDIR": rebuild_path, "INCLUDE_DIR": rebuild_path / "include"},
    ).strip()


def diffoscope_multithread():
    """Run diffoscope over non reproducible files in all available threads"""

    (results_path / "packages").mkdir(exist_ok=True, parents=True)

    # Collect all unreproducible results
    unreproducible_results = []
    for kind in ["images", "packages"]:
        for result in getattr(suite, kind).unreproducible:
            print(f"Compare {kind}/{result.name}")
            unreproducible_results.append(result)

    # Use multiprocessing Pool to run diffoscope in parallel
    if unreproducible_results:
        with Pool(processes=cpu_count()) as pool:
            # with Pool(processes=1) as pool:
            pool.map(diffoscope, unreproducible_results)


def rebuild():
    clone_git()
    setup_version_buildinfo()
    setup_feeds_buildinfo()
    checkout_commit()
    update_feeds()
    apply_patches()
    setup_config_buildinfo()
    setup_kernelmagic()
    make_download()

    profiles_origin = parse_profiles(f"{origin_url}/{target_dir}/profiles.json")

    make("tools/tar/compile")
    make("tools/install")
    make("toolchain/install")
    make("target/compile")
    make("package/compile")
    make("package/install")
    make("package/index", "CONFIG_SIGNED_PACKAGES=")
    make("target/install")
    make("buildinfo", "V=s")
    make("json_overview_image_info", "V=s", j=1)
    make("checksum", "V=s")

    compare_profiles(profiles_origin)
    compare_packages_base()
    compare_packages_target()

    (results_path / "base").mkdir(exist_ok=True, parents=True)
    Path(results_path / "output.json").write_text(
        json.dumps({rebuild_version: {target: asdict(suite)}}, indent="    ")
    )

    if use_diffoscope:
        diffoscope_multithread()


if __name__ == "__main__":
    rebuild()
