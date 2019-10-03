# OpenWrt rebuilder

[![pipeline status](https://gitlab.com/aparcar/openwrt-rebuilder/badges/master/pipeline.svg)](https://gitlab.com/aparcar/openwrt-rebuilder/-/commits/master)
![CI](https://github.com/aparcar/openwrt-rebuilder/workflows/CI/badge.svg)


Rebuild and verify binaries released by OpenWrt.org.

## Running

Be sure to have all default OpenWrt building dependencies installed. To run the
rebuilder simply type the following command:

    openwrt-rebuilder

The following `env` variables are possible to change the rebuilders behavior:

    # target to be build
    TARGET # default: "ath79/generic"

    # version to be build
    VERSION # default:  "SNAPSHOT"

    # branch to be build
    BRANCH # default:  "master"

    # where to build OpenWrt
    REBUILD_DIR # default:  Path.cwd() / "rebuild"

    # where to find the origin builds
    ORIGIN_URL # default:  "https://downloads.cdn.openwrt.org"

    # where to get the openwrt source git
    OPENWRT_GIT # default:  "https://github.com/openwrt/openwrt.git"

    # run diffoscope on unreproducible files
    USE_DIFFOSCOPE # default:  False

    # number of cores to use
    j # default:  cpu_count() + 1

    # where to store rendered html and diffoscope output
    RESULTS_DIR # default:  Path.cwd() / "results"

For Diffoscope results it is possible to run the script within the Docker
container `aparcar/rebuild-diffoscope` or install Diffoscope directly.

The output of the script is a single
[rbvf.json](https://github.com/aparcar/reproducible-builds-verification-format)
file.
