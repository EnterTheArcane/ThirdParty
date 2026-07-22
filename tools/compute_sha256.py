"""
compute_sha256.py - Download new recipe tarballs and compute sha256 hashes.

Run from D:\O3DE\Engine\Tools\ThirdParty:
    python tools\compute_sha256.py
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from dataclasses import dataclass


@dataclass
class RecipeUpdate:
    name: str
    old_version: str
    new_version: str
    new_url: str
    drop_patches: bool = False


UPDATES: list[RecipeUpdate] = [
    # Phase 1 - simple version bumps
    RecipeUpdate("alembic",         "1.8.8",   "1.8.11",
        "https://github.com/alembic/alembic/archive/refs/tags/1.8.11.tar.gz",
        drop_patches=True),
    RecipeUpdate("assimp",          "6.0.2",   "6.0.5",
        "https://github.com/assimp/assimp/archive/refs/tags/v6.0.5.tar.gz"),
    RecipeUpdate("c4core",          "0.2.5",   "0.3.0",
        "https://github.com/biojppm/c4core/releases/download/v0.3.0/c4core-0.3.0-src.tgz",
        drop_patches=True),
    RecipeUpdate("directx-headers", "1.618.2", "1.619.1",
        "https://github.com/microsoft/DirectX-Headers/archive/refs/tags/v1.619.1.tar.gz"),
    RecipeUpdate("dirent",          "1.24",    "1.26",
        "https://github.com/tronkko/dirent/archive/1.26.tar.gz"),
    RecipeUpdate("double-conversion","3.3.0",  "3.4.0",
        "https://github.com/google/double-conversion/archive/refs/tags/v3.4.0.tar.gz"),
    RecipeUpdate("fast-float",      "8.1.0",   "8.2.5",
        "https://github.com/fastfloat/fast_float/archive/refs/tags/v8.2.5.tar.gz"),
    RecipeUpdate("harfbuzz",        "12.3.0",  "14.2.0",
        "https://github.com/harfbuzz/harfbuzz/releases/download/14.2.0/harfbuzz-14.2.0.tar.xz"),
    RecipeUpdate("icu",             "78.2",    "78.3",
        "https://github.com/unicode-org/icu/releases/download/release-78.3/icu4c-78.3-sources.tgz",
        drop_patches=True),
    RecipeUpdate("jansson",         "2.14",    "2.15.0",
        "https://github.com/akheron/jansson/releases/download/v2.15.0/jansson-2.15.0.tar.bz2"),
    RecipeUpdate("kuba-zip",        "0.3.2",   "0.3.8",
        "https://github.com/kuba--/zip/archive/v0.3.8.tar.gz"),
    RecipeUpdate("little-cms",      "2.17",    "2.19.1",
        "https://github.com/mm2/Little-CMS/releases/download/lcms2.19.1/lcms2-2.19.1.tar.gz"),
    RecipeUpdate("libde265",        "1.0.15",  "1.0.19",
        "https://github.com/strukturag/libde265/releases/download/v1.0.19/libde265-1.0.19.tar.gz"),
    RecipeUpdate("libffi",          "3.4.8",   "3.5.2",
        "https://github.com/libffi/libffi/releases/download/v3.5.2/libffi-3.5.2.tar.gz",
        drop_patches=True),
    RecipeUpdate("libheif",         "1.20.1",  "1.22.0",
        "https://github.com/strukturag/libheif/releases/download/v1.22.0/libheif-1.22.0.tar.gz"),
    RecipeUpdate("libwebm",         "1.0.0.31","1.0.0.32",
        "https://github.com/webmproject/libwebm/archive/refs/tags/libwebm-1.0.0.32.tar.gz"),
    RecipeUpdate("luau",            "0.700",   "0.722",
        "https://github.com/luau-lang/luau/archive/0.722.tar.gz"),
    RecipeUpdate("manifold",        "3.2.1",   "3.5.0",
        "https://github.com/elalish/manifold/archive/refs/tags/v3.5.0.tar.gz",
        drop_patches=True),
    RecipeUpdate("md4c",            "0.5.2",   "0.5.3",
        "https://github.com/mity/md4c/archive/refs/tags/release-0.5.3.tar.gz",
        drop_patches=True),
    RecipeUpdate("meshoptimizer",   "1.0",     "1.1",
        "https://github.com/zeux/meshoptimizer/archive/refs/tags/v1.1.tar.gz"),
    RecipeUpdate("msdfgen",         "1.12",    "1.13",
        "https://github.com/Chlumsky/msdfgen/archive/refs/tags/v1.13.tar.gz"),
    RecipeUpdate("ogg",             "1.3.5",   "1.3.6",
        "https://github.com/xiph/ogg/archive/refs/tags/v1.3.6.tar.gz"),
    RecipeUpdate("openal-soft",     "1.23.1",  "1.25.2",
        "https://github.com/kcat/openal-soft/releases/download/1.25.2/openal-soft-1.25.2.tar.bz2"),
    RecipeUpdate("openddl-parser",  "0.5.1",   "0.5.2",
        "https://github.com/kimkulling/openddl-parser/archive/v0.5.2.tar.gz"),
    RecipeUpdate("openjph",         "0.27.0",  "0.27.3",
        "https://github.com/aous72/OpenJPH/archive/0.27.3.tar.gz",
        drop_patches=True),
    RecipeUpdate("pcre2",           "10.44",   "10.47",
        "https://github.com/PCRE2Project/pcre2/releases/download/pcre2-10.47/pcre2-10.47.tar.bz2"),
    RecipeUpdate("ptex",            "2.4.2",   "2.5.2",
        "https://github.com/wdas/ptex/archive/refs/tags/v2.5.2.tar.gz",
        drop_patches=True),
    RecipeUpdate("pybind11",        "3.0.1",   "3.0.4",
        "https://github.com/pybind/pybind11/archive/v3.0.4.tar.gz"),
    RecipeUpdate("pystring",        "1.1.4",   "1.1.5",
        "https://github.com/imageworks/pystring/archive/refs/tags/v1.1.5.tar.gz"),
    RecipeUpdate("rapidyaml",       "0.10.0",  "0.13.0",
        "https://github.com/biojppm/rapidyaml/releases/download/v0.13.0/rapidyaml-0.13.0-src.tgz",
        drop_patches=True),
    RecipeUpdate("re2c",            "4.3",     "4.5.1",
        "https://github.com/skvadrik/re2c/releases/download/4.5.1/re2c-4.5.1.tar.xz"),
    RecipeUpdate("strawberryperl",  "5.40.2.1","5.42.2.1",
        "https://github.com/StrawberryPerl/Perl-Dist-Strawberry/releases/download/SP_54221_64bit/strawberry-perl-5.42.2.1-64bit-portable.zip"),
    RecipeUpdate("robin-map",       "1.4.0",   "1.4.1",
        "https://github.com/Tessil/robin-map/archive/v1.4.1.tar.gz"),
    RecipeUpdate("utfcpp",          "4.0.9",   "4.1.1",
        "https://github.com/nemtrif/utfcpp/archive/v4.1.1.tar.gz"),
    # Phase 2 - major upgrades (sha256 only, code changes done separately)
    RecipeUpdate("catch2",          "2.13.10", "3.15.0",
        "https://github.com/catchorg/Catch2/archive/v3.15.0.tar.gz"),
    RecipeUpdate("joltphysics",     "3.0.1",   "5.5.0",
        "https://github.com/jrouwe/JoltPhysics/archive/refs/tags/v5.5.0.tar.gz",
        drop_patches=True),
    RecipeUpdate("openssl",         "3.6.2",   "4.0.0",
        "https://github.com/openssl/openssl/releases/download/openssl-4.0.0/openssl-4.0.0.tar.gz"),
]


def sha256_of_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=120) as resp:
        while chunk := resp.read(65536):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    results: list[tuple[str, str, str, str, bool]] = []
    errors: list[tuple[str, str]] = []

    for u in UPDATES:
        print(f"  Fetching {u.name} {u.new_version} ...", flush=True)
        try:
            digest = sha256_of_url(u.new_url)
            results.append((u.name, u.new_version, u.new_url, digest, u.drop_patches))
            print(f"    OK  {digest[:16]}...", flush=True)
        except Exception as exc:
            errors.append((u.name, str(exc)))
            print(f"    ERROR: {exc}", flush=True)

    print("\n--- RESULTS ---")
    for name, new_ver, url, digest, drop in results:
        drop_str = " [drop_patches]" if drop else ""
        print(f"{name}|{new_ver}|{url}|{digest}{drop_str}")

    if errors:
        print("\n--- ERRORS ---")
        for name, msg in errors:
            print(f"{name}: {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
