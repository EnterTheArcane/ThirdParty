import json
from functools import cached_property

import requests

from thirdparty._internal.model.version import Version
from thirdparty.recipe import RecipeBase


class GoogleSourceRepository:
    def __init__(self, recipe: RecipeBase, url: str) -> None:
        self._recipe = recipe
        self._url = url.rstrip("/")

    @cached_property
    def latest_release(self) -> str:
        resp = requests.get(f"{self._url}/+refs/tags?format=JSON", timeout=30)
        resp.raise_for_status()
        text = resp.text
        if text.startswith(")]}"):
            text = text[text.index("\n") + 1:]
        data = json.loads(text)
        best_tag: str | None = None
        best_version: Version | None = None
        for ref in data:
            # Gitiles may return full "refs/tags/v1.2.3" or bare "v1.2.3" names.
            if ref.startswith("refs/tags/"):
                tag = ref.removeprefix("refs/tags/")
            elif ref.startswith("refs/") or ref == "HEAD":
                continue
            else:
                tag = ref
            try:
                v = Version(tag.lstrip("v"))
            except Exception:
                continue
            if not v.main or not all(isinstance(item.value, int) for item in v.main):
                continue
            if best_version is None or v > best_version:
                best_version = v
                best_tag = tag
        if best_tag is None:
            raise RuntimeError(f"no version-like tags found at {self._url}")
        return best_tag
