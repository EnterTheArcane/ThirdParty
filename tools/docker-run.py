#!/usr/bin/env python3
"""Run a `thirdparty` command inside a fresh, temporary Linux Docker container.

The repo is mounted at /o3de so the framework runs from the mounted source via PYTHONPATH=src, but
the heavy build tree (/o3de/build) is a Docker NAMED VOLUME rather than part of the host bind mount.
On Docker Desktop (WSL2) the host bind mount reaches the Windows filesystem through a slow 9p/virtiofs
layer, which cripples the "touch thousands of tiny files" pattern of archive extraction and CMake
configure. The named volume lives on the VM's native ext4 (near-native speed) and still persists across
--rm runs, so single-recipe rebuilds keep all their already-built deps. The container is removed on exit.

Usage:
  python tools/docker-run.py build zlib
  python tools/docker-run.py build --target-arch ARM zlib
  python tools/docker-run.py list
  python tools/docker-run.py --rebuild build zlib   # (re)build the image first
  python tools/docker-run.py --shell                # drop into an interactive shell
  python tools/docker-run.py --no-build-volume ...  # write build/ to the host bind mount instead

Build outputs live inside the `o3de-build` volume (not on the host build/ folder). Inspect/extract
them via the container, e.g. `python tools/docker-run.py --shell` then `ls build/<recipe>/linux-x64`.

The image is built automatically the first time (or with --rebuild) using the repo root as the
build context so the Dockerfile can read pyproject.toml.
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO / "containers" / "linux" / "Dockerfile"
IMAGE = "o3de/thirdparty:linux"
# Persist the framework's source/tool download cache across --rm runs via a Docker named volume
# (mounted at CACHE_MOUNT; O3DE_THIRDPARTY_CACHE points the downloader at it). Sources are extracted
# into the mounted build/ tree already; this keeps the raw tarballs (incl. the prebuilt cmake/ninja)
# from being re-downloaded every run.
CACHE_VOLUME = "o3de-thirdparty-cache"
CACHE_MOUNT = "/cache"
# Keep the heavy build tree on a fast in-VM named volume (see module docstring) instead of the slow
# host bind mount. Persists across --rm runs so incremental single-recipe rebuilds stay fast.
BUILD_VOLUME = "o3de-build"
BUILD_MOUNT = "/o3de/build"


def _image_exists(image: str) -> bool:
    return subprocess.run(
        ["docker", "image", "inspect", image],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def _build_image(image: str) -> None:
    print(f"[docker-run] building image {image} ...", file=sys.stderr)
    subprocess.check_call(
        ["docker", "build", "-t", image, "-f", str(DOCKERFILE), str(REPO)])


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run a thirdparty command inside a temporary Linux Docker container.",
        epilog="Everything after the options is forwarded to `thirdparty` (use -- to be explicit).")
    ap.add_argument("--image", default=IMAGE, help=f"Docker image tag (default: {IMAGE})")
    ap.add_argument("--rebuild", action="store_true", help="(Re)build the image before running")
    ap.add_argument("--shell", action="store_true",
                    help="Start an interactive shell instead of running a command")
    ap.add_argument("--cache-volume", default=CACHE_VOLUME,
                    help=f"Docker named volume for the download cache (default: {CACHE_VOLUME})")
    ap.add_argument("--no-cache", action="store_true",
                    help="Do not mount the persistent download-cache volume")
    ap.add_argument("--build-volume", default=BUILD_VOLUME,
                    help=f"Docker named volume for the build tree (default: {BUILD_VOLUME})")
    ap.add_argument("--no-build-volume", action="store_true",
                    help="Write build/ to the host bind mount instead of the fast named volume")
    ap.add_argument("command", nargs=argparse.REMAINDER,
                    help="The thirdparty command and arguments (e.g. build zlib)")
    args = ap.parse_args()

    if subprocess.run(["docker", "--version"],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        print("[docker-run] error: docker is not available on PATH", file=sys.stderr)
        return 1

    if args.rebuild or not _image_exists(args.image):
        _build_image(args.image)

    mount = f"{REPO}:/o3de"
    docker = ["docker", "run", "--rm", "-v", mount, "-w", "/o3de"]
    if not args.no_build_volume:
        # Named volume shadows the bind-mounted build/ subdir with fast in-VM storage.
        docker += ["-v", f"{args.build_volume}:{BUILD_MOUNT}"]
    if not args.no_cache:
        # The named volume is created automatically on first use.
        docker += ["-v", f"{args.cache_volume}:{CACHE_MOUNT}",
                   "-e", f"O3DE_THIRDPARTY_CACHE={CACHE_MOUNT}"]
    if sys.stdin.isatty() and sys.stdout.isatty():
        docker.append("-it")

    if args.shell:
        return subprocess.call(docker + [args.image])

    fwd = args.command
    if fwd and fwd[0] == "--":
        fwd = fwd[1:]
    if not fwd:
        print("[docker-run] error: no thirdparty command given (try `build zlib` or --shell)",
              file=sys.stderr)
        return 2

    inner = "PYTHONPATH=src python3 -m thirdparty " + " ".join(shlex.quote(a) for a in fwd)
    return subprocess.call(docker + [args.image, "-c", inner])


if __name__ == "__main__":
    raise SystemExit(main())
