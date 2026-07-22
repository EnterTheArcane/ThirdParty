#!/usr/bin/env python3
"""port_data.py - Convert a conan-center-index recipe_data.yml to ThirdParty data.yml.

Usage::

    python tools/port_data.py <recipe-name> [options]

The script reads::

    <cci_root>/recipes/<name>/all/recipe_data.yml

and writes::

    <thirdparty_root>/recipes/<name>/data.yml

It also copies any patch files referenced in the recipe_data.yml patches section
to ``<thirdparty_root>/recipes/<name>/patches/``.

By default only the **latest** (first) version is ported.  Use ``--all-versions``
to include all versions found in recipe_data.yml.

Options:
  --cci-root PATH       Path to conan-center-index (default: auto-detect)
  --out-root PATH       Path to ThirdParty recipes root (default: ./recipes)
  --all-versions        Port every version, not just the latest
  --dry-run             Print result to stdout instead of writing file
  --overwrite           Overwrite existing data.yml (default: skip if present)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    print("ERROR: pyyaml is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# ===========================================================================
# Conversion logic
# ===========================================================================

def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data: Any = yaml.safe_load(f)
    if not isinstance(data, dict):
        return {}
    return data  # type: ignore[return-value]


def _convert(
    recipe_data: dict[str, Any],
    all_versions: bool,
    source_dir: Path,
    out_dir: Path,
) -> dict[str, Any]:
    """Convert recipe_data.yml dict → thirdparty data.yml dict.

    Also copies patch files from *source_dir*/patches/ to *out_dir*/patches/.
    """
    sources: Any = recipe_data.get("sources", {})
    patches_raw: Any = recipe_data.get("patches", {})

    if not isinstance(sources, dict):
        raise ValueError("recipe_data.yml 'sources' key is not a dict")

    version_keys = list(sources.keys())
    if not version_keys:
        raise ValueError("recipe_data.yml has no versions under 'sources'")

    selected = version_keys if all_versions else [version_keys[0]]

    versions_out: dict[str, Any] = {}
    patches_out: dict[str, list[str]] = {}

    for ver in selected:
        ver_str = str(ver)
        src_info: Any = sources[ver]
        if not isinstance(src_info, dict):
            continue

        # Build the versions entry
        ver_entry: dict[str, Any] = {}
        if "url" in src_info:
            url = src_info["url"]
            # Some recipes store url as a list (mirrors); take the first
            if isinstance(url, list):
                url = url[0]
            ver_entry["url"] = url
        if "sha256" in src_info:
            ver_entry["sha256"] = src_info["sha256"]

        versions_out[ver_str] = ver_entry

        # Handle patches
        if isinstance(patches_raw, dict) and ver in patches_raw:
            ver_patches: Any = patches_raw[ver]
            if isinstance(ver_patches, list):
                patch_names: list[str] = []
                for p in ver_patches:
                    if not isinstance(p, dict):
                        continue
                    patch_file: Any = p.get("patch_file", "")
                    if not patch_file:
                        continue
                    # patch_file is relative to the recipe folder in CCI
                    # e.g. "patches/0001-fix.patch"
                    patch_names.append(str(patch_file))

                    # Copy the actual patch file if it exists
                    src_patch = source_dir / str(patch_file)
                    if src_patch.exists():
                        dst_patch = out_dir / str(patch_file)
                        dst_patch.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_patch, dst_patch)
                        print(f"[port_data] Copied patch: {patch_file}")
                    else:
                        print(
                            f"[port_data] WARNING: patch file not found: {src_patch}",
                            file=sys.stderr,
                        )

                if patch_names:
                    patches_out[ver_str] = patch_names

    result: dict[str, Any] = {"versions": versions_out}
    if patches_out:
        result["patches"] = patches_out
    return result


def _dump_yaml(data: dict[str, Any]) -> str:
    return yaml.dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


# ===========================================================================
# CLI
# ===========================================================================

def _find_cci_root() -> Path:
    candidates = [
        Path(r"D:\OpenSource\conan-center-index"),
        Path(__file__).parent.parent.parent.parent.parent / "OpenSource" / "conan-center-index",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    raise RuntimeError(
        "Cannot auto-detect conan-center-index root. Pass --cci-root explicitly."
    )


def port_data(
    name: str,
    cci_root: Path,
    out_root: Path,
    all_versions: bool = False,
    dry_run: bool = False,
    overwrite: bool = False,
) -> None:
    # Locate recipe_data.yml
    recipe_dir = cci_root / "recipes" / name / "all"
    if not recipe_dir.is_dir():
        # Try first versioned folder
        candidates = sorted((cci_root / "recipes" / name).glob("*/recipe_data.yml"))
        if not candidates:
            print(f"ERROR: recipe_data.yml not found for {name!r}", file=sys.stderr)
            sys.exit(1)
        recipe_data_path = candidates[0]
        recipe_dir = recipe_data_path.parent
    else:
        recipe_data_path = recipe_dir / "recipe_data.yml"
        if not recipe_data_path.exists():
            print(f"ERROR: {recipe_data_path} not found", file=sys.stderr)
            sys.exit(1)

    out_dir = out_root / name
    out_path = out_dir / "data.yml"

    if not overwrite and out_path.exists() and not dry_run:
        print(f"[port_data] SKIP {name} - {out_path} already exists (use --overwrite)")
        return

    recipe_data = _load_yaml(recipe_data_path)
    converted = _convert(recipe_data, all_versions, recipe_dir, out_dir)
    output = _dump_yaml(converted)

    if dry_run:
        print(f"# data.yml for {name}")
        print(output)
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")
    print(f"[port_data] Wrote {out_path}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Convert recipe_data.yml to ThirdParty data.yml format."
    )
    parser.add_argument("name", help="Recipe name (e.g. zlib-ng)")
    parser.add_argument("--cci-root", default=None, metavar="PATH")
    parser.add_argument(
        "--out-root",
        default=None,
        metavar="PATH",
        help="ThirdParty recipes/ directory (default: ./recipes)",
    )
    parser.add_argument("--all-versions", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")

    args = parser.parse_args(argv)

    cci_root = Path(args.cci_root) if args.cci_root else _find_cci_root()
    if args.out_root:
        out_root = Path(args.out_root)
    else:
        out_root = Path(__file__).parent.parent / "recipes"

    port_data(
        name=args.name,
        cci_root=cci_root,
        out_root=out_root,
        all_versions=args.all_versions,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()
