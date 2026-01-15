# OpenWrt rebuilder

![CI](https://github.com/aparcar/openwrt-rebuilder/workflows/CI/badge.svg)

Rebuild and verify binaries released by OpenWrt.org.

## Requirements

- [uv](https://docs.astral.sh/uv/) package manager
- OpenWrt build dependencies (build-essential, git, etc.)

## Running

To run the rebuilder using uv:

```sh
uv run openwrt-rebuilder
```

## Configuration

The following environment variables control the rebuilder's behavior:

| Variable         | Default                         | Description                                                                  |
| ---------------- | ------------------------------- | ---------------------------------------------------------------------------- |
| `TARGET`         | `x86/64`                        | Target architecture (e.g., `ath79/generic`, `mediatek/filogic`)              |
| `VERSION`        | `SNAPSHOT`                      | OpenWrt version to build                                                     |
| `SOURCE_MIRROR`  | `https://codeberg.org/openwrt/` | Mirror for OpenWrt git sources (also supports `https://github.com/openwrt/`) |
| `ORIGIN_URL`     | `https://downloads.openwrt.org` | URL for official OpenWrt builds                                              |
| `REBUILD_DIR`    | `./build/{VERSION}`             | Build directory                                                              |
| `RESULTS_DIR`    | `./results/{VERSION}/{TARGET}`  | Output directory for results                                                 |
| `DL_PATH`        | `{REBUILD_DIR}/dl`              | Downloads directory                                                          |
| `USE_DIFFOSCOPE` | `True`                          | Run diffoscope on unreproducible files                                       |
| `j`              | CPU count + 1                   | Number of parallel build jobs                                                |

### Example

```sh
TARGET=mediatek/filogic VERSION=SNAPSHOT uv run openwrt-rebuilder
```

To use GitHub instead of Codeberg as the source mirror:

```sh
SOURCE_MIRROR=https://github.com/openwrt/ uv run openwrt-rebuilder
```

## Diffoscope

For diffoscope analysis, either:

- Run within the `aparcar/rebuild-diffoscope` Docker container
- Install diffoscope directly on the system

## Output

The script produces a [rbvf.json](https://github.com/aparcar/reproducible-builds-verification-format) file containing the verification results.
