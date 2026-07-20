# OpenWrt rebuilder

![Tests](https://github.com/aparcar/openwrt-rebuilder/actions/workflows/test.yml/badge.svg)

Rebuild binaries released by OpenWrt.org.

The tool rebuilds an OpenWrt artifact and writes the result into an output
directory. It does not compare anything itself — the caller does that, either
[rebuilderd](https://github.com/kpcyrd/rebuilderd) (which byte-compares the
output against the published files) or you, locally. So you can test a rebuild
on your own without running a rebuilderd instance.

## Requirements

- [uv](https://docs.astral.sh/uv/) package manager
- OpenWrt build dependencies (build-essential, git, etc.)
- `gpg` and `tar` for the package command (SDK signature check + unpack)

## Usage

Everything is passed as CLI parameters; the tool reads no environment variables.

### Rebuild a firmware target

Checks out openwrt.git with full history, restores the release `.config` and pins
the feeds from the published `*.buildinfo`, then builds the whole target from
source the way OpenWrt's buildbots do:

```sh
uv run openwrt-rebuilder firmware \
    --target x86/64 \
    --release SNAPSHOT \
    --output ./out
```

| Option            | Default                         | Description                                                |
| ----------------- | ------------------------------- | ---------------------------------------------------------- |
| `--target`        | *required*                      | Target/subtarget, e.g. `x86/64`, `mediatek/filogic`        |
| `--release`       | *required*                      | `SNAPSHOT`, or e.g. `24.10.0` / `24.10-SNAPSHOT`           |
| `--output`        | *required*                      | Where to write rebuilt artifacts (and build logs)          |
| `-j`, `--jobs`    | CPU count + 1                   | Number of parallel build jobs                              |
| `--build-dir`     | `./build/{release}`             | Build tree                                                 |
| `--dl-dir`        | `{build-dir}/dl`                | Source download cache                                      |
| `--source-mirror` | `https://codeberg.org/openwrt/` | Git mirror for OpenWrt sources                             |
| `--origin-url`    | `https://downloads.openwrt.org` | Origin URL for published OpenWrt builds                    |

### Rebuild a single apk package

Downloads and GPG-verifies the matching OpenWrt SDK, unpacks it, pins the feeds
from the target's `feeds.buildinfo`, and compiles just that one package:

```sh
uv run openwrt-rebuilder package \
    --package tmate-2.4.0-r3.apk \
    --target x86/64 \
    --release SNAPSHOT \
    --output ./out
```

| Option          | Default                                    | Description                                          |
| --------------- | ------------------------------------------ | ---------------------------------------------------- |
| `--package`     | *required*                                 | apk filename; the package name is parsed from it     |
| `--target`      | *required*                                 | Target/subtarget of the SDK, e.g. `x86/64`           |
| `--release`     | *required*                                 | `SNAPSHOT`, or e.g. `24.10.0`                        |
| `--output`      | *required*                                 | Where to write the rebuilt `.apk`                    |
| `--upstream`    | `https://downloads.openwrt.org`            | Base download URL                                    |
| `--sdk-cache`   | `~/.cache/rebuilderd-openwrt-sdk`          | Cache for verified SDK tarballs                      |
| `--dl-dir`      | `~/.cache/rebuilderd-openwrt-dl`           | OpenWrt source download cache                        |
| `--keyring-dir` | `/usr/local/share/rebuilderd/openwrt-keys` | Directory of OpenWrt GPG public keys                 |

An apk carries neither its target nor the release, so both must be passed
explicitly. The published apk URL names the *package architecture*
(`.../packages/<arch>/<feed>/<file>.apk`), which is not a target: several
ABI-compatible targets share one arch, and the SDK is published per target. That
mapping belongs to the calling tooling (e.g. rebuilderd's OpenWrt backend), not
here — pick any target for the arch and pass it in.

## Checking the result

Compare the rebuilt artifacts in `--output` against the published ones, e.g.:

```sh
curl -sO https://downloads.openwrt.org/snapshots/packages/x86_64/base/tmate-2.4.0-r3.apk
diffoscope tmate-2.4.0-r3.apk ./out/tmate-2.4.0-r3.apk
```
