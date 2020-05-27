#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright © 2019 Paul Spooren <mail@aparcar.org>
#
# Based on the reproducible_openwrt.sh
#   © 2014-2019 Holger Levsen <holger@layer-acht.org>
#   © 2015 Reiner Herrmann <reiner@reiner-h.de>
#   © 2016-2018 Alexander Couzens <lynxis@fe80.eu>
#
# Released under the GPLv2

import email.parser
import json
import re
from datetime import datetime
from multiprocessing import Pool, cpu_count
from os import environ, symlink
from pathlib import Path
from shutil import rmtree
from subprocess import run
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

rebuilder = {
    "maintainer": environ.get("REBUILDER_MAINTAINER", "unknown"),
    "contact": environ.get("REBUILDER_CONTACT", "unknown"),
    "name": environ.get("REBUILDER_NAME", "unknown"),
    "uri": environ.get("REBUILDER_URI", "unknown"),
}


# target to be build
target = environ.get("TARGET", "ath79/generic").replace("-", "/")

# version to be build
rebuild_version = environ.get("VERSION", "SNAPSHOT")

# where to build OpenWrt
rebuild_path = Path(environ.get("REBUILD_DIR", Path.cwd() / "rebuild"))

bin_path = rebuild_path / "bin/targets"

dl_path = Path(environ.get("DL_PATH", rebuild_path / "dl"))

# where to find the origin builds
origin_url = environ.get("ORIGIN_URL", "https://downloads.cdn.openwrt.org")

# where to get the openwrt source git
openwrt_git = environ.get("OPENWRT_GIT", "https://github.com/openwrt/openwrt.git")

use_diffoscope = environ.get("USE_DIFFOSCOPE", False)

# number of cores to use
j = environ.get("j", cpu_count() + 1)

# where to store rendered html and diffoscope output
results_path = Path(environ.get("RESULTS_DIR", Path.cwd() / "results"))


if rebuild_version == "SNAPSHOT":
    print("Using snapshots/")
    target_dir = f"snapshots/targets/{target}"
    branch = "master"
else:
    print(f"Using releases/{rebuild_version}/")
    target_dir = f"releases/{rebuild_version}/targets/{target}"
    branch = f'openwrt-{rebuild_version.rsplit(".", maxsplit=1)[0]}'

# ignore everything except packages and images
ignore_files = re.compile(
    "|".join(
        [
            "kernel-debug.tar.bz2",
            "openwrt-imagebuilder",
            "openwrt-sdk",
            "sha256sums.sig",
        ]
    )
)

rbvf = {
    "origin_uri": origin_url,
    "origin_name": "openwrt",
    "results": [],
    "rebuilder": rebuilder,
}


def run_command(cmd, cwd=".", ignore_errors=False, capture=False, env={}, timeout=None):
    """
    Run a command in shell
    """
    print("Running {} in {}".format(cmd, cwd))
    current_env = environ.copy()
    current_env.update(env)
    proc = run(
        cmd,
        cwd=cwd,
        capture_output=capture,
        text=True,
        env=current_env,
        timeout=timeout,
    )

    if proc.returncode and not ignore_errors:
        print("Error running {}".format(cmd))
        quit()

    if capture:
        print(proc.stderr)
        return proc.stdout


# return content of online file or stores it locally if path is given
def get_file(url, path=None):
    print(f"Downloading {url}")
    try:
        content = urlopen(url).read()
    except Exception as e:
        print(e)
        return 1

    if path:
        print("storing to {}".format(path))
        Path(path).write_bytes(content)
        return 0
    else:
        return content.decode()


# parse the origin sha256sums file from openwrt
def parse_sha256sums(path: Path):
    return {v: k for k, v in re.findall(r"(.+?) \*(.+?)\n", path.read_text())}


def parse_origin_sha256sums():
    get_file(
        f"{origin_url}/{target_dir}/sha256sums", rebuild_path / "sha256sums_origin",
    )
    return parse_sha256sums(rebuild_path / "sha256sums_origin")


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
        config_content + "\nCONFIG_COLLECT_KERNEL_DEBUG=n\nCONFIG_IB=n\nCONFIG_SDK=n\n"
    )
    make("defconfig")


def setup_feeds_buildinfo():
    # download origin buildinfo file containing the feeds
    feeds = get_file(f"{origin_url}/{target_dir}/feeds.buildinfo",)
    feeds = feeds.replace("git.openwrt.org/project/luci", "github.com/openwrt/luci")
    feeds = feeds.replace(
        "git.openwrt.org/feed/routing", "github.com/openwrt-routing/packages"
    )
    feeds = feeds.replace(
        "git.openwrt.org/feed/telephony", "github.com/openwrt/telephony"
    )
    feeds = feeds.replace(
        "git.openwrt.org/feed/packages", "github.com/openwrt/packages"
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


def setup_key():
    """Add fake but reproducible keys"""

    # insecure private key to build the images
    (rebuild_path / "key-build").write_text("# fake private key")

    (rebuild_path / "key-build.ucert").write_text("# fake certificate")

    # spoof the official openwrt public key to prevent adding another key in the binary
    if rebuild_version == "SNAPSHOT":
        usign_key = "OpenWrt snapshot release signature\n"
        usign_key += "RWS1BD5w+adc3j2Hqg9+b66CvLR7NlHbsj7wjNVj0XGt/othDgIAOJS+"
    else:
        usign_key = "OpenWrt 19.07 release signature\n"
        usign_key += "RWT5S53W/rrJY9BiIod3JF04AZ/eU1xDpVOb+rjZzAQBEcoETGx8BXEK"

    (rebuild_path / "key-build.pub").write_text(usign_key)

    # this specific key is odly chmodded to 600
    (rebuild_path / "key-build.pub").chmod(0o600)


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


def add_kmods_feed():
    """Add kmod feed to image

    Snapshot builds contain a special feeds pointing to compatible kmods
    """
    target_staging_dir = Path(
        run_command(
            ["make", "--no-print-directory", "val.STAGING_DIR_ROOT"],
            rebuild_path,
            capture=True,
            env={"TOPDIR": rebuild_path, "INCLUDE_DIR": rebuild_path / "include"},
        ).strip()
    )

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

    distfeeds_orig = (target_staging_dir / "etc/opkg/distfeeds.conf").read_text()

    distfeeds_kmods = re.sub(
        r"^(src/gz .*)_core (.*)/packages\n",
        r"\1_core \2/packages\n\1_kmods \2/kmods/{}\n".format(kernelversion),
        distfeeds_orig,
        re.MULTILINE,
    )

    print(distfeeds_kmods)
    (rebuild_path / "files/etc/opkg").mkdir(parents=True, exist_ok=True)
    (rebuild_path / "files/etc/opkg/distfeeds.conf").write_text(distfeeds_kmods)


def make(*cmd):
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
        capture=True,
    )


def add_result(component, target, name, version, cpe, status, artifacts):
    rbvf["results"].append(
        {
            "suite": rebuild_version,
            "component": component,
            "target": target,
            "build_date": int(datetime.utcnow().timestamp()),
            "name": name,
            "version": version,
            "cpe": cpe,
            "status": status,
            "artifacts": artifacts,
        }
    )


def parse_origin_packages():
    get_file(
        f"{origin_url}/{target_dir}/packages/Packages", rebuild_path / "Packages",
    )
    packages = {}
    linebuffer = ""
    for line in (rebuild_path / "Packages").read_text().splitlines():
        if line == "":
            parser = email.parser.Parser()
            package = parser.parsestr(linebuffer)
            packages[package["Filename"]] = package
            linebuffer = ""
        else:
            linebuffer += line + "\n"
    return packages


def compare_checksums(origin_sha256sums, origin_packages):
    # iterate over all sums in origin sha256sums and check rebuild files
    rebuild_sha256sums = parse_sha256sums(bin_path / target / "sha256sums")

    for origin_name, origin_sum in origin_sha256sums.items():
        # except the meta files defined above
        if ignore_files.match(origin_name):
            print(f"Skipping file {origin_name}")
            continue

        print("checking {}".format(origin_name))
        artifacts = {}

        # files ending with ipk are considered packages
        if origin_name.startswith("packages/"):
            if not origin_name.endswith(".ipk"):
                continue

            status = "untested"

            pkg = origin_packages.get(origin_name.split("/")[1], {})
            if not pkg:
                print(f"ERROR: {origin_name} not in upstream Packages")
                continue

            if origin_name not in rebuild_sha256sums:
                status = "notfound"
            elif origin_sum != rebuild_sha256sums[origin_name]:
                status = "unreproducible"
                try:
                    artifacts["buildlog_uri"] = str(
                        results_path
                        / "logs/package"
                        / pkg["Section"]
                        / pkg["Package"]
                        / "compile.txt"
                    )
                except:
                    print(dict(pkg))

                artifacts["diffoscope_html_uri"] = f"{origin_name}.html"
                artifacts["binary_uri"] = f"{origin_name}"
            else:
                status = "reproducible"
            add_result(
                "packages",
                target,
                pkg.get("Package"),
                pkg.get("Version"),
                pkg.get("CPE-ID", ""),
                status,
                artifacts,
            )
        else:
            if origin_name not in rebuild_sha256sums:
                status = "notfound"
            elif origin_sum != rebuild_sha256sums[origin_name]:
                status = "unreproducible"
                artifacts["diffoscope_html_uri"] = f"{origin_name}.html"
                artifacts["binary_uri"] = f"{origin_name}"
            else:
                status = "reproducible"
            add_result(
                "images", target, origin_name, commit, "", status, artifacts,
            )

    Path(results_path / "rbvf.json").write_text(json.dumps(rbvf, indent="    "))
    run_command(["gzip", "-f", "-k", "rbvf.json"], results_path)


def make_download():
    if rebuild_path / "dl" != dl_path and not dl_path.exists():
        print(f'Symlink {rebuild_path / "dl"} -> {dl_path.absolute()}')
        symlink(
            dl_path.absolute(), rebuild_path / "dl",
        )

    make("download")


def diffoscope(result):
    """
    Download file from openwrt server and compare it, store in output_path
    """
    origin_file = NamedTemporaryFile()
    download_url = f'{origin_url}/{target_dir}/{result["artifacts"]["binary_uri"]}'

    if not (bin_path / target / result["artifacts"]["binary_uri"]).is_file():
        return

    if get_file(download_url, origin_file.name):
        print("Error downloading {}".format(download_url))
        return

    run_command(
        [
            "diffoscope",
            origin_file.name,
            bin_path / target / result["artifacts"]["binary_uri"],
            "--html",
            str(results_path / result["artifacts"]["binary_uri"]) + ".html",
        ],
        ignore_errors=True,
        timeout=180,
    )

    origin_file.close()


def diffoscope_multithread():
    """Run diffoscope over non reproducible files in all available threads"""

    (results_path / "packages").mkdir(exist_ok=True, parents=True)
    pool = Pool(cpu_count() + 1)
    pool.map(
        diffoscope, filter(lambda x: x["status"] == "unreproducible", rbvf["results"]),
    )


def rebuild():
    clone_git()
    setup_version_buildinfo()
    setup_feeds_buildinfo()
    checkout_commit()
    update_feeds()
    setup_config_buildinfo()
    make("clean", "V=s")
    make_download()
    origin_packages = parse_origin_packages()
    origin_sha256sums = parse_origin_sha256sums()
    setup_key()
    make("tools/tar/compile")
    make("tools/install")
    make("toolchain/install")
    make("target/compile")
    make("package/compile")
    make("package/install")
    make("package/index", "CONFIG_SIGNED_PACKAGES=")
    if rebuild_version == "SNAPSHOT":
        add_kmods_feed()
    make("target/install")
    make("buildinfo", "V=s")
    make("json_overview_image_info")
    make("checksum", "V=s")
    compare_checksums(origin_sha256sums, origin_packages)
    if use_diffoscope:
        diffoscope_multithread()


if __name__ == "__main__":
    rebuild()
