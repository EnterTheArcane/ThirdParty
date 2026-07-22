"""Extract current version and URL patterns from recipes."""
import re
import sys
from pathlib import Path

recipes_dir = Path(__file__).parent.parent / "recipes"
targets = [
    "alembic", "assimp", "autoconf", "automake", "c4core",
    "directx-headers", "dirent", "double-conversion", "fast-float",
    "fontconfig", "freetype", "gdbm", "glib", "harfbuzz", "icu",
    "jansson", "kuba-zip", "libaom-av1", "libde265", "libffi",
    "gettext", "libheif", "libiconv", "libjpeg-turbo", "libsvtav1",
    "libtool", "libwebm", "libxml2", "luau", "m4", "manifold", "md4c",
    "meshoptimizer", "msdfgen", "ogg", "openal-soft", "openddl-parser",
    "openjph", "opus", "pcre2", "ptex", "pybind11", "pystring",
    "rapidyaml", "re2c", "spirv-headers", "strawberryperl",
    "robin-map", "utfcpp", "vulkan-headers",
    "vulkan-utility-libraries", "vulkan-validation-layers",
    "wayland", "wayland-protocols",
]

for name in targets:
    p = recipes_dir / name / "recipe.py"
    if not p.exists():
        print(f"{name}: MISSING")
        continue
    txt = p.read_text()
    m_ver = re.search(r'version\s*=\s*"([^"]+)"', txt)
    cur = m_ver.group(1) if m_ver else "?"
    # find f-string or plain url in get() call
    m_url = re.search(r'url\s*=\s*f"([^"]+)"', txt)
    if not m_url:
        m_url = re.search(r'url\s*=\s*"(https?://[^"]+)"', txt)
    url = m_url.group(1) if m_url else "?"
    print(f"{name}|{cur}|{url}")
