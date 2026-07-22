import re
from functools import cached_property

import requests

from thirdparty._internal.model.version import Version
from thirdparty.recipe import RecipeBase


class WebReleaseIndex:
    """Extract the highest stable version from a first-party HTTP index."""

    def __init__(self, recipe: RecipeBase, url: str) -> None:
        self._recipe = recipe
        self._url = url

    @cached_property
    def text(self) -> str:
        response = requests.get(self._url, timeout=30)
        response.raise_for_status()
        return response.text

    def latest_release(
        self,
        pattern: str,
        group: int | str = 1,
        flags: int = 0) -> str:
        """Return the highest non-prerelease version captured by *pattern*."""
        best_value: str | None = None
        best_version: Version | None = None
        for match in re.finditer(pattern, self.text, flags):
            value = match.group(group)
            try:
                # Archive filenames frequently use underscores as numeric separators
                # (for example jom_1_1_7.zip).
                version = Version(value.replace("_", "."))
            except Exception:
                continue
            if version.pre is not None:
                continue
            if best_version is None or version > best_version:
                best_version = version
                best_value = value
        if best_value is None:
            raise RuntimeError(f"no version matching {pattern!r} found at {self._url}")
        return best_value


class SourceForgeProject:
    """Read SourceForge's official best-release JSON endpoint."""

    def __init__(self, recipe: RecipeBase, project: str) -> None:
        self._recipe = recipe
        self._project = project

    def latest_release(self, pattern: str, group: int | str = 1) -> str:
        url = f"https://sourceforge.net/projects/{self._project}/best_release.json"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        filename = response.json()["release"]["filename"]
        match = re.search(pattern, filename)
        if match is None:
            raise RuntimeError(
                f"release filename {filename!r} does not match {pattern!r} for {self._project}")
        return match.group(group)


class NugetPackage:
    """Read stable package versions from NuGet's v3 flat-container API."""

    def __init__(self, recipe: RecipeBase, package: str) -> None:
        self._recipe = recipe
        self._package = package.lower()

    @property
    def latest_release(self) -> str:
        url = f"https://api.nuget.org/v3-flatcontainer/{self._package}/index.json"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        best_value: str | None = None
        best_version: Version | None = None
        for value in response.json().get("versions", []):
            version = Version(value)
            if version.pre is not None:
                continue
            if best_version is None or version > best_version:
                best_version = version
                best_value = value
        if best_value is None:
            raise RuntimeError(f"no stable versions found for NuGet package {self._package}")
        return best_value
