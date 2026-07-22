"""Check which outdated recipes have patches folders."""
from pathlib import Path

recipes_dir = Path(r"D:\O3DE\Engine\Tools\ThirdParty\recipes")
names = [
    "alembic", "assimp", "c4core", "directx-headers", "dirent",
    "double-conversion", "fast-float", "harfbuzz", "icu", "jansson",
    "kuba-zip", "little-cms", "libde265", "libffi", "libheif", "libwebm",
    "luau", "manifold", "md4c", "meshoptimizer", "msdfgen", "ogg",
    "openal-soft", "openddl-parser", "openjph", "pcre2", "ptex",
    "pybind11", "pystring", "rapidyaml", "re2c", "strawberryperl",
    "robin-map", "utfcpp",
]
for name in names:
    p = recipes_dir / name / "patches"
    if p.exists():
        files = [f.name for f in p.iterdir()]
        print(f"{name}: {files}")
    else:
        print(f"{name}: no patches")
