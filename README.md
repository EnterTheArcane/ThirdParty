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

Packaging: `oci` (OCI images) and `archive` (plain archives) consume the *already-built* staged
package under `build/<name>/<package_id>/package/`. They never run a recipe build - if the package
isn't built yet, they fail (run `thirdparty build <name>` first).

Archives:
```bash
# A single compressed archive + a metadata.json sidecar. --format: tar, tar.gz (default),
# tar.bz2, tar.xz, zip.
thirdparty archive zlib                    # -> build/zlib/<id>/dist/zlib-<ver>-<id>.tar.gz
thirdparty archive zlib --format zip
thirdparty archive "*" --format tar.xz     # every built recipe
```

OCI images:
```bash
# 1. Build the OCI image as an on-disk image layout (blobs + index.json), single layer,
#    no Docker/daemon required.
thirdparty oci build zlib                   # -> build/zlib/<id>/dist/oci/

# 2. Push a BUILT layout to any OCI registry as <registry>/<owner>/<prefix>/<name> (--registry
#    default ghcr.io; also docker.io, quay.io, GitLab, Harbor, self-hosted registry:2). Fails if
#    'oci build' hasn't run. Always writes only a per-platform tag <version>-<os>-<arch>, never
#    the shared multi-arch tag, so a parallel CI matrix never races. Run on each matrix runner.
#    Auth is discovered from the registry's WWW-Authenticate challenge (Bearer or Basic);
#    credentials, first match wins: --username/--password -> GH_TOKEN/GITHUB_TOKEN (ghcr.io) ->
#    REGISTRY_USERNAME + REGISTRY_PASSWORD/REGISTRY_TOKEN -> ~/.docker/config.json -> ~/.netrc.
export GH_TOKEN=...                         # ghcr.io default; or `docker login <registry>`
thirdparty oci push zlib --owner o3de
thirdparty oci push zlib --registry docker.io --owner myorg --username myorg --password "$PAT"

# 3. Combine - (re)assembles the multi-arch <version> tag from every per-platform tag now in the
#    registry, so consumers pull one tag and get their os/arch (Homebrew-bottle style). Run once
#    at the end of the pipeline. Additive/idempotent upsert: rerun for just one os/arch and it
#    refreshes that platform while preserving the rest. Needs only recipes/ + network (no build).
thirdparty oci combine zlib --owner o3de

# 4. Pull - download an image and extract it into a directory CMake consumers can use
#    (CMAKE_PREFIX_PATH / find_package). --platform defaults to the current machine; it selects the
#    matching entry from the multi-arch index. Public images pull anonymously (no credentials).
#    The <image> is a full URI or a bare recipe name (composed with --registry/--owner/--prefix/--tag).
thirdparty oci pull ghcr.io/o3de/thirdparty/zlib:1.3.2 --output ./zlib   # -> ./zlib/{include,lib,...}
thirdparty oci pull ghcr.io/o3de/thirdparty/zlib:1.3.2 --platform linux/arm64 -o ./zlib
thirdparty oci pull zlib --owner o3de --tag 1.3.2 --output ./zlib        # name mode
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

