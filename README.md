# ThirdParty

Setup:
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/macOS
pip install -e "."
```

Usage:
```bash
thirdparty --help
thirdparty list
thirdparty build
```

Packaging:
```bash
# Turn a built/staged package into a distributable artifact. Backends:
#   oci (default) - a single-layer OCI image written as an on-disk image layout
#                   (blobs + index.json), no Docker/daemon required
#   tar.gz / zip  - a plain archive plus a metadata.json sidecar
thirdparty package zlib                      # -> build/zlib/<package_id>/dist/oci/
thirdparty package zlib --format tar.gz      # -> build/zlib/<package_id>/dist/zlib-<ver>-<id>.tar.gz
thirdparty package "*"                        # package every built recipe

# Publish the OCI image to a container registry (GHCR) as ghcr.io/<owner>/<prefix>/<name>:<version>.
# Repeated per-platform publishes accrete into one multi-arch index tag, so consumers pull one
# tag and the registry resolves their os/arch (Homebrew-bottle style). Needs GH_TOKEN or
# GITHUB_TOKEN with packages:write.
export GH_TOKEN=...                            # or GITHUB_TOKEN
thirdparty publish zlib --owner o3de --dry-run # print the planned registry calls
thirdparty publish zlib --owner o3de           # push (owner defaults to $GITHUB_REPOSITORY_OWNER)
```

Type checking:
```bash
pyright
```

Docker (Linux builds):
```bash
# Run a thirdparty command inside a temporary Linux container (builds the image on first use):
python tools/docker-run.py build zlib
python tools/docker-run.py --shell        # interactive shell in the container

# The heavy build tree (/o3de/build) lives on a fast in-VM Docker named volume (o3de-build), NOT the
# host bind mount: on Docker Desktop/WSL2 the host mount reaches the Windows filesystem through a slow
# 9p/virtiofs layer that cripples archive extraction and CMake configure. The volume is near-native
# speed and persists across runs, so single-recipe rebuilds keep their already-built deps.
# Build outputs live in the volume (not the host build/ folder) - inspect via --shell. Use
# --no-build-volume to write to the host bind mount instead.

# Source/tool downloads (incl. the prebuilt cmake/ninja) are cached in a Docker named volume
# (o3de-thirdparty-cache) so they are not re-fetched every run. Use --no-cache to skip it.

# Or drive Docker directly (build context is the repo root so the image can read pyproject.toml):
docker build -t o3de/thirdparty:linux -f containers/linux/Dockerfile .
docker run --rm -it -v $(pwd):/o3de -v o3de-build:/o3de/build -w /o3de o3de/thirdparty:linux \
    -c "PYTHONPATH=src python3 -m thirdparty build zlib"
```

