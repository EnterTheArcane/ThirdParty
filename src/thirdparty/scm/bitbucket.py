import re
from functools import cached_property
from typing import Any

import requests

from thirdparty._internal.model.version import Version
from thirdparty.recipe import RecipeBase


class BitbucketRepository:
    def __init__(self, recipe: RecipeBase, slug: str) -> None:
        self._recipe = recipe
        self._slug = slug

    @cached_property
    def latest_release(self) -> str:
        return self._highest_tag()

    def _highest_tag(self) -> str:
        best_tag: str | None = None
        best_version: Version | None = None
        url: str | None = f"https://api.bitbucket.org/2.0/repositories/{self._slug}/tags"
        params: dict[str, Any] = {"pagelen": 100}
        while url:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for tag in data.get("values", []):
                name: str = tag["name"]
                stripped = re.sub(r"^\D+", "", name)
                if not stripped:
                    continue
                try:
                    v = Version(stripped)
                except Exception:
                    continue
                if not v.main or not all(isinstance(item.value, int) for item in v.main):
                    continue
                if best_version is None or v > best_version:
                    best_version = v
                    best_tag = name
            url = data.get("next")
            params = {}
        if best_tag is None:
            raise RuntimeError(f"no version-like tags found for {self._slug}")
        return best_tag
