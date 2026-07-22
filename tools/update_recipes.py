"""update_recipes.py - Apply all version updates to recipe.py files."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

RECIPES_DIR = Path(__file__).resolve().parent.parent / "recipes"

@dataclass
class RecipeUpdate:
    name: str
    old_version: str
    new_version: str
    old_url: str
    new_url: str
    old_sha256: str
    new_sha256: str
    drop_patches: bool = False
    extra_replacements: list[tuple[str, str]] = field(default_factory=list)


# All sha256 values computed from download.
# old_sha256 extracted from current recipe files.
UPDATES: list[RecipeUpdate] = [
    RecipeUpdate(
        "alembic", "1.8.8", "1.8.11",
        "https://github.com/alembic/alembic/archive/refs/tags/1.8.8.tar.gz",
        "https://github.com/alembic/alembic/archive/refs/tags/1.8.11.tar.gz",
        "ba1f34544608ef7d3f68cafea946ec9cc84792ddf9cda3e8d5590821df71f6c6",
        "ab299bb4b1894a6675c73fa29940522b54c81a91b1d691ca3470d86b7345ffce",
        drop_patches=True,
    ),
    RecipeUpdate(
        "assimp", "6.0.2", "6.0.5",
        "https://github.com/assimp/assimp/archive/refs/tags/v6.0.2.tar.gz",
        "https://github.com/assimp/assimp/archive/refs/tags/v6.0.5.tar.gz",
        "", "edf3749559c2b7d1f758ffb66fc5bec62186221e623b7f2e8969f17ee46ecb6f",
    ),
    RecipeUpdate(
        "c4core", "0.2.5", "0.3.0",
        "https://github.com/biojppm/c4core/releases/download/v0.2.5/c4core-0.2.5-src.tgz",
        "https://github.com/biojppm/c4core/releases/download/v0.3.0/c4core-0.3.0-src.tgz",
        "", "47a5634c785f84a6bef07c04c3cc3c063ff61c5c7554b95c35298712e2f306fd",
        drop_patches=True,
    ),
    RecipeUpdate(
        "directx-headers", "1.618.2", "1.619.1",
        "https://github.com/microsoft/DirectX-Headers/archive/refs/tags/v1.618.2.tar.gz",
        "https://github.com/microsoft/DirectX-Headers/archive/refs/tags/v1.619.1.tar.gz",
        "", "6193774904c940eebb9b0c51b816b93dd776cfeb25a951f0f4a58f22387e5008",
    ),
    RecipeUpdate(
        "dirent", "1.24", "1.26",
        "https://github.com/tronkko/dirent/archive/1.24.tar.gz",
        "https://github.com/tronkko/dirent/archive/1.26.tar.gz",
        "", "a91662ee5243d2dae5aee7ed8527f95097afda517cc5cc7ca2699648a74a419c",
    ),
    RecipeUpdate(
        "double-conversion", "3.3.0", "3.4.0",
        "https://github.com/google/double-conversion/archive/refs/tags/v3.3.0.tar.gz",
        "https://github.com/google/double-conversion/archive/refs/tags/v3.4.0.tar.gz",
        "", "42fd4d980ea86426e457b24bdfa835a6f5ad9517ddb01cdb42b99ab9c8dd5dc9",
    ),
    RecipeUpdate(
        "fast-float", "8.1.0", "8.2.5",
        "https://github.com/fastfloat/fast_float/archive/refs/tags/v8.1.0.tar.gz",
        "https://github.com/fastfloat/fast_float/archive/refs/tags/v8.2.5.tar.gz",
        "", "17c7fb14499fcf42c3f5d143df0fbe22172e92749ec5f75ef13224005421a654",
    ),
    RecipeUpdate(
        "harfbuzz", "12.3.0", "14.2.0",
        "https://github.com/harfbuzz/harfbuzz/releases/download/12.3.0/harfbuzz-12.3.0.tar.xz",
        "https://github.com/harfbuzz/harfbuzz/releases/download/14.2.0/harfbuzz-14.2.0.tar.xz",
        "", "94017020f96d025bb66ae91574e4cf334bcad23e8175a8a40565b3721bc2eaff",
    ),
    RecipeUpdate(
        "icu", "78.2", "78.3",
        "https://github.com/unicode-org/icu/releases/download/release-78.2/icu4c-78.2-sources.tgz",
        "https://github.com/unicode-org/icu/releases/download/release-78.3/icu4c-78.3-sources.tgz",
        "", "3a2e7a47604ba702f345878308e6fefeca612ee895cf4a5f222e7955fabfe0c0",
        drop_patches=True,
    ),
    RecipeUpdate(
        "jansson", "2.14", "2.15.0",
        "https://github.com/akheron/jansson/releases/download/v2.14/jansson-2.14.tar.bz2",
        "https://github.com/akheron/jansson/releases/download/v2.15.0/jansson-2.15.0.tar.bz2",
        "", "a7eac7765000373165f9373eb748be039c10b2efc00be9af3467ec92357d8954",
    ),
    RecipeUpdate(
        "kuba-zip", "0.3.2", "0.3.8",
        "https://github.com/kuba--/zip/archive/v0.3.2.tar.gz",
        "https://github.com/kuba--/zip/archive/v0.3.8.tar.gz",
        "", "944656c33aa776dc2c882991d1a6a86c8408fec8b8a19bc5305bf7eabdd4d908",
    ),
    RecipeUpdate(
        "little-cms", "2.17", "2.19.1",
        "https://github.com/mm2/Little-CMS/releases/download/lcms2.17/lcms2-2.17.tar.gz",
        "https://github.com/mm2/Little-CMS/releases/download/lcms2.19.1/lcms2-2.19.1.tar.gz",
        "", "bfc54f7bab59fbc921012014a8032e4cba4abd46db47d46b76416a8c0b2815c8",
    ),
    RecipeUpdate(
        "libde265", "1.0.15", "1.0.19",
        "https://github.com/strukturag/libde265/releases/download/v1.0.15/libde265-1.0.15.tar.gz",
        "https://github.com/strukturag/libde265/releases/download/v1.0.19/libde265-1.0.19.tar.gz",
        "", "bb19a0b485d2643e0eeb7e91f3ab32d1ad617e7c487dbedc91214ca3dbd8d7eb",
    ),
    RecipeUpdate(
        "libffi", "3.4.8", "3.5.2",
        "https://github.com/libffi/libffi/releases/download/v3.4.8/libffi-3.4.8.tar.gz",
        "https://github.com/libffi/libffi/releases/download/v3.5.2/libffi-3.5.2.tar.gz",
        "", "f3a3082a23b37c293a4fcd1053147b371f2ff91fa7ea1b2a52e335676bac82dc",
        drop_patches=True,
    ),
    RecipeUpdate(
        "libheif", "1.20.1", "1.22.0",
        "https://github.com/strukturag/libheif/releases/download/v1.20.1/libheif-1.20.1.tar.gz",
        "https://github.com/strukturag/libheif/releases/download/v1.22.0/libheif-1.22.0.tar.gz",
        "", "8bd20cfa3201997b8f63266cddfabea2e1481467d7f992e6a2595e0bec691fc2",
    ),
    RecipeUpdate(
        "libwebm", "1.0.0.31", "1.0.0.32",
        "https://github.com/webmproject/libwebm/archive/refs/tags/libwebm-1.0.0.31.tar.gz",
        "https://github.com/webmproject/libwebm/archive/refs/tags/libwebm-1.0.0.32.tar.gz",
        "", "7fd5e085bda9f8031cf2ad2a1e52d9b7b29cba9c0b96ad2ce794ce89e4249eb8",
    ),
    RecipeUpdate(
        "luau", "0.700", "0.722",
        "https://github.com/luau-lang/luau/archive/0.700.tar.gz",
        "https://github.com/luau-lang/luau/archive/0.722.tar.gz",
        "", "b69d7dd42540dc3892c5aa2f5c733897a8350ad64f09a0e0984a8c42ba29961b",
    ),
    RecipeUpdate(
        "manifold", "3.2.1", "3.5.0",
        "https://github.com/elalish/manifold/archive/refs/tags/v3.2.1.tar.gz",
        "https://github.com/elalish/manifold/archive/refs/tags/v3.5.0.tar.gz",
        "", "7002091f992c80bec49b69e49c85769d862bb97169781e23b9909a4b72b6a618",
        drop_patches=True,
    ),
    RecipeUpdate(
        "md4c", "0.5.2", "0.5.3",
        "https://github.com/mity/md4c/archive/refs/tags/release-0.5.2.tar.gz",
        "https://github.com/mity/md4c/archive/refs/tags/release-0.5.3.tar.gz",
        "", "353c346f376b87c954a13f3415ede2d51264cc61dc5abcd38ff1d2aa0d059b9e",
        drop_patches=True,
    ),
    RecipeUpdate(
        "meshoptimizer", "1.0", "1.1",
        "https://github.com/zeux/meshoptimizer/archive/refs/tags/v1.0.tar.gz",
        "https://github.com/zeux/meshoptimizer/archive/refs/tags/v1.1.tar.gz",
        "", "b787011f81b4b3069c2f9065b7c191efdd4189a49be32ba5282dd5579f05261a",
    ),
    RecipeUpdate(
        "msdfgen", "1.12", "1.13",
        "https://github.com/Chlumsky/msdfgen/archive/refs/tags/v1.12.tar.gz",
        "https://github.com/Chlumsky/msdfgen/archive/refs/tags/v1.13.tar.gz",
        "", "93cd1ad8918c1a78c5c96e82d4f4c77f0eb86c2e7e8579a0967e54196c4b7167",
    ),
    RecipeUpdate(
        "ogg", "1.3.5", "1.3.6",
        "https://github.com/xiph/ogg/archive/refs/tags/v1.3.5.tar.gz",
        "https://github.com/xiph/ogg/archive/refs/tags/v1.3.6.tar.gz",
        "", "95b643da661155d79db9de2fca55daed3a8d491039829def246aacb3d9201c81",
    ),
    RecipeUpdate(
        "openal-soft", "1.23.1", "1.25.2",
        "https://github.com/kcat/openal-soft/releases/download/1.23.1/openal-soft-1.23.1.tar.bz2",
        "https://github.com/kcat/openal-soft/archive/refs/tags/1.25.2.tar.gz",
        "", "fb27e5839aa11f0e5b9d33756965291fad5d6909ab928ea1f796f4a1a6877894",
    ),
    RecipeUpdate(
        "openddl-parser", "0.5.1", "0.5.2",
        "https://github.com/kimkulling/openddl-parser/archive/v0.5.1.tar.gz",
        "https://github.com/kimkulling/openddl-parser/archive/v0.5.2.tar.gz",
        "", "8058caacdc989a010c2ad3ab62df99f9f3034b4981649c5fb832efa6fbf10c36",
    ),
    RecipeUpdate(
        "openjph", "0.27.0", "0.27.3",
        "https://github.com/aous72/OpenJPH/archive/0.27.0.tar.gz",
        "https://github.com/aous72/OpenJPH/archive/0.27.3.tar.gz",
        "", "f96808ef72cf3acca73a52123bda3e680f6550dfb4774ad7de57eb3ce26de57a",
        drop_patches=True,
    ),
    RecipeUpdate(
        "pcre2", "10.44", "10.47",
        "https://github.com/PCRE2Project/pcre2/releases/download/pcre2-10.44/pcre2-10.44.tar.bz2",
        "https://github.com/PCRE2Project/pcre2/releases/download/pcre2-10.47/pcre2-10.47.tar.bz2",
        "", "47fe8c99461250d42f89e6e8fdaeba9da057855d06eb7fc08d9ca03fd08d7bc7",
    ),
    RecipeUpdate(
        "ptex", "2.4.2", "2.5.2",
        "https://github.com/wdas/ptex/archive/refs/tags/v2.4.2.tar.gz",
        "https://github.com/wdas/ptex/archive/refs/tags/v2.5.2.tar.gz",
        "", "dd95fbea4b50e9e68fd042f540fb83157a0ff25053066c3439d4527de3621d34",
        drop_patches=True,
    ),
    RecipeUpdate(
        "pybind11", "3.0.1", "3.0.4",
        "https://github.com/pybind/pybind11/archive/v3.0.1.tar.gz",
        "https://github.com/pybind/pybind11/archive/v3.0.4.tar.gz",
        "", "74b6a2c2b4573a400cafb6ecbf60c98df300cd3d0041296b913d02b2cbbb2676",
    ),
    RecipeUpdate(
        "pystring", "1.1.4", "1.1.5",
        "https://github.com/imageworks/pystring/archive/refs/tags/v1.1.4.tar.gz",
        "https://github.com/imageworks/pystring/archive/refs/tags/v1.1.5.tar.gz",
        "", "63c30c251b8017c897bd923826f400aee1d6e4f1c22ffbbd2104f150522a2040",
    ),
    RecipeUpdate(
        "rapidyaml", "0.10.0", "0.13.0",
        "https://github.com/biojppm/rapidyaml/releases/download/v0.10.0/rapidyaml-0.10.0-src.tgz",
        "https://github.com/biojppm/rapidyaml/releases/download/v0.13.0/rapidyaml-0.13.0-src.tgz",
        "", "b70b484b612152b0dbb2ca61178c9534d80c392fe36d4d54e75d127ec8864d52",
        drop_patches=True,
    ),
    RecipeUpdate(
        "re2c", "4.3", "4.5.1",
        "https://github.com/skvadrik/re2c/releases/download/4.3/re2c-4.3.tar.xz",
        "https://github.com/skvadrik/re2c/releases/download/4.5.1/re2c-4.5.1.tar.xz",
        "", "ffea067c11aa668bcb42885be6e6cd000302000b7747d2bb213299ec66b7864e",
    ),
    RecipeUpdate(
        "strawberryperl", "5.40.2.1", "5.42.2.1",
        "https://github.com/StrawberryPerl/Perl-Dist-Strawberry/releases/download/SP_54021_64bit_UCRT/strawberry-perl-5.40.2.1-64bit-portable.zip",
        "https://github.com/StrawberryPerl/Perl-Dist-Strawberry/releases/download/SP_54221_64bit/strawberry-perl-5.42.2.1-64bit-portable.zip",
        "", "32d83be90cf04b807cfb9477482bc36302cdee6f5b04cf57e81adecbd8f07898",
    ),
    RecipeUpdate(
        "robin-map", "1.4.0", "1.4.1",
        "https://github.com/Tessil/robin-map/archive/v1.4.0.tar.gz",
        "https://github.com/Tessil/robin-map/archive/v1.4.1.tar.gz",
        "", "0e3f53a377fdcdc5f9fed7a4c0d4f99e82bbb64175233bd13427fef9a771f4a1",
    ),
    RecipeUpdate(
        "utfcpp", "4.0.9", "4.1.1",
        "https://github.com/nemtrif/utfcpp/archive/v4.0.9.tar.gz",
        "https://github.com/nemtrif/utfcpp/archive/v4.1.1.tar.gz",
        "", "1ca68016f0abc24172998e39ce0d8f8e2b7a26f7579a0ff85d4e1b9a7aea56f8",
    ),
]


def apply_update(update: RecipeUpdate) -> bool:
    path = RECIPES_DIR / update.name / "recipe.py"
    if not path.exists():
        print(f"  SKIP: {path} not found")
        return False

    original = path.read_text(encoding="utf-8")
    text = original

    # 1. Update version string in class body
    text = re.sub(
        r'(^\s*version\s*=\s*")' + re.escape(update.old_version) + r'"',
        r'\g<1>' + update.new_version + '"',
        text,
        flags=re.MULTILINE,
    )

    # 2. Replace the URL
    if update.old_url and update.old_url in text:
        text = text.replace(update.old_url, update.new_url)
    else:
        # Fallback: replace just the old version string in any URL line
        text = re.sub(
            r'(url\s*=\s*["\'])([^"\']*?)' + re.escape(update.old_version),
            lambda m: m.group(1) + m.group(2) + update.new_version,
            text,
        )

    # 3. Replace sha256 - if we know the old one, replace it; otherwise replace any 64-char hex after sha256=
    if update.old_sha256 and update.old_sha256 in text:
        text = text.replace(update.old_sha256, update.new_sha256)
    else:
        # Replace the sha256 value that appears right after the URL we just set
        # Strategy: find sha256="<64hex>" anywhere and replace with new value
        # Only if the new URL already appears (so we know we're in the right recipe)
        text = re.sub(
            r'(sha256\s*=\s*")[0-9a-f]{64}(")',
            r'\g<1>' + update.new_sha256 + r'\g<2>',
            text,
            count=1,
        )

    # 4. Apply any extra replacements (e.g., for _SOURCE_URL/_SOURCE_SHA256)
    for old_str, new_str in update.extra_replacements:
        text = text.replace(old_str, new_str)

    # 5. Remove apply_patches(self) if requested
    if update.drop_patches:
        # Remove the line containing apply_patches(self)
        lines = text.splitlines(keepends=True)
        new_lines = [
            ln for ln in lines
            if "apply_patches(self)" not in ln
        ]
        text = "".join(new_lines)

    if text == original:
        print(f"  WARNING: no changes made to {update.name}")
        return False

    path.write_text(text, encoding="utf-8")
    changes = []
    if update.old_version != update.new_version:
        changes.append(f"{update.old_version} -> {update.new_version}")
    if update.drop_patches:
        changes.append("dropped apply_patches")
    print(f"  OK  {update.name}: {', '.join(changes)}")
    return True


def main() -> None:
    ok = 0
    fail = 0
    for u in UPDATES:
        if apply_update(u):
            ok += 1
        else:
            fail += 1
    print(f"\nDone: {ok} updated, {fail} skipped/failed")


if __name__ == "__main__":
    main()
