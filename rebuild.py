#!/usr/bin/env python3

import os
import re
import pystache
import re
import subprocess
import hashlib
from urllib.request import urlopen
from tempfile import mkdtemp, NamedTemporaryFile
from multiprocessing import cpu_count
from multiprocessing import Pool
from time import strftime, gmtime
import shutil
import importlib
import json

# target to be build
target = os.environ.get("TARGET", "ath79/generic")
# version to be build
version = os.environ.get("VERSION", "SNAPSHOT")
# where to (re)build openwrt
# rebuild_dir = os.environ.get("REBUILD_DIR", mkdtemp())
rebuild_dir = os.environ.get("REBUILD_DIR", "/builder/shared-workdir/build")
# where to find mustache templates
template_dir = os.environ.get("TEMPLATE_DIR", "templates")
# where to find the origin builds
openwrt_url = (
    os.environ.get("ORIGIN_URL", "https://downloads.openwrt.org/snapshots/targets/")
    + target
)

# where to store rendered html and diffoscope output
output_dir = os.environ.get("OUTPUT_DIR", "./output/")
# dir of the version + target
output_target_dir = os.path.join(output_dir, version, target)

# dir where openwrt actually stores binary files
target_dir = rebuild_dir + "/bin/targets/" + target
# where to get the openwrt source git
openwrt_git = os.environ.get("OPENWRT_GIT", "https://github.com/openwrt/openwrt.git")

# run a command in shell
def run_command(cmd, cwd=".", ignore_errors=False, env={}):
    print("Running {} in {}".format(cmd, cwd))
    current_env = os.environ.copy()
    current_env.update(env)
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, env=current_env)
    response = ""
    # print and store the output at the same time
    while True:
        line = proc.stdout.readline().decode("utf-8")
        if line == "" and proc.poll() != None:
            break
        response += line
        print(line, end="", flush=True)

    if proc.returncode and not ignore_errors:
        print("Error running {}".format(cmd))
        quit()
    return response


# files not to check via diffoscope
meta_files = re.compile(
    "|".join(
        [
            ".+\.buildinfo",
            ".+\.manifest",
            "openwrt-imagebuilder",
            "openwrt-sdk",
            "sha256sums",
            "kernel-debug.tar.bz2",
        ]
    )
)

# the context to fill the mustache tempaltes
context = {
    "root": "https://rebuild.aparcar.org",
    "targets": [
        {"version": "SNAPSHOT", "name": "ath79/generic"},
        {"version": "SNAPSHOT", "name": "x86/64"},
        {"version": "SNAPSHOT", "name": "ramips/mt7621"},
        {"version": "SNAPSHOT", "name": "ramips/mt7620"},
    ],
    "version": version,
    "commit_string": "",
    "images_repro": 0,
    "images_repro_percent": 0,
    "kernelversion": "unknown",
    "images_total": 0,
    "packages_repro": 0,
    "packages_repro_percent": 0,
    "packages_total": 0,
    "today": strftime("%Y-%m-%d", gmtime()),
    "diffoscope_version": run_command(["diffoscope", "--version"]).split()[1],
    "target": target,
    "images": [],
    "packages": [],
    "git_log_oneline": "",
    "missing": [],
}

# download file from openwrt server and compare it, store output in output_target_dir
def diffoscope(origin_name):
    file_origin = NamedTemporaryFile()

    if get_file(openwrt_url + "/" + origin_name, file_origin.name):
        print("Error downloading {}".format(origin_name))
        return

    run_command(
        [
            "diffoscope",
            file_origin.name,
            target_dir + "/" + origin_name,
            "--html",
            output_target_dir + "/" + origin_name + ".html",
        ],
        ignore_errors=True,
    )
    shutil.move(target_dir + "/" + origin_name, output_target_dir + "/" + origin_name)
    file_origin.close()


# return sha256sum of given path
def sha256sum(path):
    with open(path, "rb") as hash_file:
        return hashlib.sha256(hash_file.read()).hexdigest()


# return content of online file or stores it locally if path is given
def get_file(url, path=None):
    print("downloading {}".format(url))
    try:
        content = urlopen(url).read()
    except:
        return 1

    if path:
        print("storing to {}".format(path))
        with open(path, "wb") as file_b:
            file_b.write(content)
        return 0
    else:
        return content.decode("utf-8")


# parse the origin sha256sums file from openwrt
def parse_origin_sha256sums():
    sha256sums = get_file(openwrt_url + "/sha256sums")
    return re.findall(r"(.+?) \*(.+?)\n", sha256sums)


def exchange_signature(origin_name):
    file_origin = NamedTemporaryFile()
    rebuild_path = target_dir + "/" + origin_name
    sig_path = rebuild_path + ".sig"

    if get_file(openwrt_url + "/" + origin_name, file_origin.name):
        print("Error downloading {}".format(origin_name))
        file_origin.close()
        return
    # extract original signatur in temporary file
    run_command(
        [
            rebuild_dir + "/staging_dir/host/bin/fwtool",
            "-s",
            sig_path,
            file_origin.name,
        ],
        ignore_errors=True,
    )
    if os.path.getsize(sig_path) > 0:
        # remove random signatur of rebuild
        run_command(
            [
                rebuild_dir + "/staging_dir/host/bin/fwtool",
                "-t",
                "-s",
                "/dev/null",
                rebuild_path,
            ],
            ignore_errors=True,
        )
        # add original signature to rebuild file
        run_command(
            [
                rebuild_dir + "/staging_dir/host/bin/fwtool",
                "-S",
                sig_path,
                rebuild_path,
            ],
            ignore_errors=True,
        )
        print("Attached origin signature to {}".format(rebuild_path))
    file_origin.close()


def clone_git():
    # initial clone of openwrt.git
    run_command(["git", "clone", openwrt_git, rebuild_dir])


def setup_buildinfo():
    # download buildinfo files
    get_file(openwrt_url + "/config.buildinfo", rebuild_dir + "/.config")
    with open(rebuild_dir + "/.config", "a") as config_file:
        # extra options used by the buildbot
        config_file.writelines(
            [
                "CONFIG_IB=n\n",
                "CONFIG_SDK=n\n",
                'CONFIG_KERNEL_BUILD_USER="builder"\n',
                'CONFIG_KERNEL_BUILD_DOMAIN="buildhost"\n',
            ]
        )

    # download origin buildinfo file containing the feeds
    get_file(openwrt_url + "/feeds.buildinfo", rebuild_dir + "/feeds.conf")

    # get current commit_string to show in website banner
    context["commit_string"] = get_file(openwrt_url + "/version.buildinfo")[:-1]
    # ... and parse the actual commit to checkout
    context["commit"] = context["commit_string"].split("-")[1]


def setup_key():
    # insecure private key to build the images
    with open(rebuild_dir + "/key-build", "w") as key_build_file:
        key_build_file.write(
            "Local build key\nRWRCSwAAAAB12EzgExgKPrR4LMduadFAw1Z8teYQAbg/EgKaN9SUNrgteVb81/bjFcvfnKF7jS1WU8cDdT2VjWE4Cp4cxoxJNrZoBnlXI+ISUeHMbUaFmOzzBR7B9u/LhX3KAmLsrPc="
        )

    # spoof the official openwrt public key to prevent adding another key in the binary
    with open(rebuild_dir + "/key-build.pub", "w") as key_build_pub_file:
        key_build_pub_file.write(
            "OpenWrt snapshot release signature\nRWS1BD5w+adc3j2Hqg9+b66CvLR7NlHbsj7wjNVj0XGt/othDgIAOJS+"
        )
    # this specific key is odly chmodded to 600
    os.chmod(rebuild_dir + "/key-build.pub", 0o600)


def checkout_commit():
    # checkout the desired commit
    run_command(["git", "checkout", "-f", context["commit"]], rebuild_dir)


def get_commit_log():
    # show the last 20 commit to have an idea what was changed lately
    context["git_log_oneline"] = run_command(
        ["git", "log", "--oneline", "-n", "20"], rebuild_dir
    )


def update_feeds():
    # do as the buildbots do
    run_command(["./scripts/feeds", "update"], rebuild_dir)
    run_command(["./scripts/feeds", "install", "-a"], rebuild_dir)
    make("defconfig")


def add_kmods_feed():
    target_staging_dir = run_command(
        ["make", "--no-print-directory", "val.STAGING_DIR_ROOT"],
        rebuild_dir,
        env={"TOPDIR": rebuild_dir, "INCLUDE_DIR": rebuild_dir + "/include"},
    )
    os.makedirs(rebuild_dir + "/files/etc/opkg/", exist_ok=True)
    context["kernelversion"] = "-".join(
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
            rebuild_dir,
            env={"TOPDIR": rebuild_dir, "INCLUDE_DIR": rebuild_dir + "/include"},
        ).splitlines()
    )
    with open(
        target_staging_dir[0:-1] + "/etc/opkg/distfeeds.conf", "r"
    ) as distfeeds_orig_file:
        distfeeds_orig = distfeeds_orig_file.read()

    print(distfeeds_orig)

    distfeeds_kmods = re.sub(
        r"^(src/gz .*)_core (.*)/packages\n",
        r"\1_core \2/packages\n\1_kmods \2/kmods/{}\n".format(context["kernelversion"]),
        distfeeds_orig,
        re.MULTILINE,
    )

    with open(rebuild_dir + "/files/etc/opkg/distfeeds.conf", "w") as distfeeds_file:
        distfeeds_file.write(distfeeds_kmods)


def make(*cmd):
    run_command(
        ["make", "IGNORE_ERRORS='n m'", "BUILD_LOG=1", "-j{}".format(cpu_count() + 1)]
        + list(cmd),
        rebuild_dir,
    )


def reset_target_output():
    # flush the current website dir of target
    shutil.rmtree(output_target_dir, ignore_errors=True)

    # and recreate it here
    os.makedirs(output_target_dir + "/packages", exist_ok=True)


def compare_checksums():
    # iterate over all sums in origin sha256sums and check rebuild files
    for origin in parse_origin_sha256sums():
        origin_sum, origin_name = origin
        # except the meta files defined above
        if meta_files.match(origin_name):
            print("Skipping meta file {}".format(origin_name))
            continue

        rebuild_path = target_dir + "/" + origin_name
        # report missing files
        if not os.path.exists(rebuild_path):
            context["missing"].append({"name": origin_name})
        else:
            print("checking {}".format(origin_name))
            rebuild_info = {
                "name": origin_name,
                "size": os.path.getsize(rebuild_path),
                "repro": False,
            }

            # files ending with ipk are considered packages
            if origin_name.endswith(".ipk"):
                rebuild_info["sha256sum"] = sha256sum(rebuild_path)
                if rebuild_info["sha256sum"] == origin_sum:
                    rebuild_info["repro"] = True
                    context["packages_repro"] += 1
                context["packages"].append(rebuild_info)
            else:
                # everything else should be images
                exchange_signature(origin_name)
                rebuild_info["sha256sum"] = sha256sum(rebuild_path)
                if rebuild_info["sha256sum"] == origin_sum:
                    rebuild_info["repro"] = True
                    context["images_repro"] += 1
                context["images"].append(rebuild_info)


def calculate_repro_stats():
    # calculate how many images are reproducible
    context["images_total"] = len(context["images"])
    if context["images_total"]:
        context["images_repro_percent"] = round(
            context["images_repro"] / context["images_total"] * 100.0, 2
        )

    # calculate how many packages are reproducible
    context["packages_total"] = len(context["packages"])
    if context["packages_total"]:
        context["packages_repro_percent"] = round(
            context["packages_repro"] / context["packages_total"] * 100.0, 2
        )

    print(
        "total_repro {}%".format(
            (context["packages_repro_percent"] + context["images_repro_percent"]) / 2
        )
    )


def render_website():
    # now render the website
    renderer = pystache.Renderer()
    mustache_header = renderer.load_template(template_dir + "/header")
    mustache_footer = renderer.load_template(template_dir + "/footer")
    mustache_target = renderer.load_template(template_dir + "/target")
    mustache_index = renderer.load_template(template_dir + "/index")

    index_html = renderer.render(mustache_header, context)
    index_html += renderer.render(mustache_index, context)
    index_html += renderer.render(mustache_footer, context)

    target_html = renderer.render(mustache_header, context)
    target_html += renderer.render(mustache_target, context)
    target_html += renderer.render(mustache_footer, context)

    # and store the files
    with open(output_dir + "/index.html", "w") as index_file:
        index_file.write(index_html)

    with open(output_target_dir + "/index.html", "w") as target_file:
        target_file.write(target_html)

    # store context for future review
    with open(output_target_dir + "/context.json", "w") as context_file:
        json.dump(context, context_file, indent="  ")


def diffoscope_multithread():
    # run diffoscope over non reproducible files in all available threads
    pool = Pool(cpu_count() + 1)
    pool.map(
        diffoscope,
        map(
            lambda x: x["name"],
            filter(lambda x: not x["repro"], context["images"] + context["packages"]),
        ),
    )


if __name__ == "__main__":
    clone_git()
    setup_buildinfo()
    checkout_commit()
    get_commit_log()
    setup_key()
    update_feeds()
    make("tools/tar/compile")
    make("tools/install")
    make("toolchain/install")
    make("target/compile")
    make("package/compile")
    make("package/install")
    make("package/index", "CONFIG_SIGNED_PACKAGES=")
    if version == "SNAPSHOT":
        add_kmods_feed()
    make("target/install")
    reset_target_output()
    compare_checksums()
    calculate_repro_stats()
    render_website()
    diffoscope_multithread()
