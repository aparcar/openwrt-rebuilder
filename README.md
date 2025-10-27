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
    REBUILD_DIR # default:  Path.cwd() / "openwrt"

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

## CI/CD Configuration

The GitHub Actions workflow runs daily at 2 AM UTC and can also be triggered manually. It supports uploading test results and build logs to an S3 bucket.

### S3 Upload Configuration

To enable S3 uploads, configure the following secrets and variables in your GitHub repository:

**Required Secrets:**
- `AWS_ACCESS_KEY_ID`: AWS access key ID with S3 write permissions
- `AWS_SECRET_ACCESS_KEY`: AWS secret access key

**Optional Variables:**
- `S3_BUCKET`: Name of the S3 bucket (required for S3 upload to work)
- `S3_PREFIX`: Prefix path in the S3 bucket (default: `openwrt-rebuilder`)
- `AWS_REGION`: AWS region for the S3 bucket (default: `us-east-1`)

The workflow uploads results to:
```
s3://<S3_BUCKET>/<S3_PREFIX>/<TIMESTAMP>/<VERSION>/<TARGET>/results/
s3://<S3_BUCKET>/<S3_PREFIX>/<TIMESTAMP>/<VERSION>/<TARGET>/logs/
```

S3 uploads only occur during scheduled runs or manual workflow dispatches, not on regular pushes to main.
