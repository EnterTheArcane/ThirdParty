import re
from functools import cached_property

import requests

from thirdparty._internal.model.version import Version
from thirdparty.recipe import RecipeBase


class GnuFtp:
    def __init__(
        self,
        recipe: RecipeBase,
        package: str,
        url: str | None = None) -> None:
        self._recipe = recipe
        self._package = package
        self._url = url or f"https://ftp.gnu.org/gnu/{package}/"

    @cached_property
    def latest_release(self) -> str:
        resp = requests.get(self._url, timeout=30)
        resp.raise_for_status()
        pattern = re.compile(
            rf"{re.escape(self._package)}-(\d[\d.]+)\.(tar\.(gz|bz2|xz|lz))")
        best_str: str | None = None
        best_version: Version | None = None
        for m in pattern.finditer(resp.text):
            try:
                v = Version(m.group(1))
            except Exception:
                continue
            if best_version is None or v > best_version:
                best_version = v
                best_str = m.group(1)
        if best_str is None:
            raise RuntimeError(f"no version found for {self._package} at {self._url}")
        return best_str
