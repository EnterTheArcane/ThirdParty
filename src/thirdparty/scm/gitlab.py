import os
import re
from functools import cached_property

import gitlab

from thirdparty._internal.model.version import Version
from thirdparty.recipe import RecipeBase


def _tag_version(tag: str) -> Version | None:
    # Strip a leading identifier+separator prefix: "vulkan-sdk-", "nasm-", "m4-", etc.
    stripped = re.sub(r"^(?:[A-Za-z][A-Za-z0-9]*[-_])+", "", tag)
    if not stripped or not stripped[0].isdigit():
        if len(tag) >= 2 and tag[0].isalpha() and tag[1].isdigit():
            stripped = tag[1:]
        else:
            return None
    had_prefix = (stripped != tag)
    candidate = stripped.replace("_", ".").replace("-", ".")
    if not candidate or not candidate[0].isdigit():
        return None
    if not re.match(r"^\d+(?:\.\d+)*$", candidate):
        return None
    try:
        v = Version(candidate)
    except Exception:
        return None
    if not v.main or not all(isinstance(i.value, int) for i in v.main):
        return None
    if len(v.main) < 2:
        return None
    main = [int(i.value) for i in v.main]
    if had_prefix and main[0] >= 1000:
        return None
    if (not had_prefix and len(main) == 3 and main[0] > 1970 and 1 <= main[1] <= 12 and 1 <= main[2] <= 31):
        return None
    return v


class GitlabRepository:
    """Typed wrapper around a single GitLab project, used by recipes.

    Usage:
        repo = GitlabRepository(self, "wayland/wayland", host="gitlab.freedesktop.org")
        repo.latest_release   # raw tag_name string, e.g. "1.24.0" or "v2.2.1"

    Authentication uses GL_TOKEN or GITLAB_TOKEN if set; otherwise anonymous.
    Unauthenticated access is subject to GitLab's rate limits and may be
    blocked on some instances without a token.
    """

    def __init__(
        self,
        recipe: RecipeBase,
        slug: str,
        host: str = "gitlab.com") -> None:
        self._recipe = recipe
        self._slug = slug
        self._host = host

    @cached_property
    def _client(self) -> gitlab.Gitlab:
        token = os.environ.get("GL_TOKEN") or os.environ.get("GITLAB_TOKEN")
        return gitlab.Gitlab(url=f"https://{self._host}", private_token=token)

    @cached_property
    def _project(self):
        return self._client.projects.get(self._slug)

    @cached_property
    def latest_release(self) -> str:
        """Raw tag_name of the latest GitLab release.

        Falls back to the highest version-like tag when the project has no
        formal releases.  When a release tag exists but _highest_tag() gives
        a strictly higher version, the tag is preferred.
        """
        releases = self._project.releases.list(
            order_by="released_at", sort="desc", per_page=1, get_all=False)
        if not releases:
            return self._highest_tag()
        release_tag = releases[0].tag_name
        try:
            ht = self._highest_tag()
            r_v = _tag_version(release_tag)
            h_v = _tag_version(ht)
            if h_v is not None and (r_v is None or h_v >= r_v):
                return ht
        except Exception:
            pass
        return release_tag

    def latest_commit_date(self, branch: str) -> str:
        commits = self._project.commits.list(ref_name=branch, per_page=1, get_all=False)
        if not commits:
            raise RuntimeError(f"no commits on {branch!r} for {self._slug} on {self._host}")
        return commits[0].created_at[:10].replace("-", "")

    @cached_property
    def latest_formal_release(self) -> str:
        """Raw tag_name of the most recently published release; no tag-scan fallback."""
        releases = self._project.releases.list(
            order_by="released_at", sort="desc", per_page=1, get_all=False)
        if not releases:
            return self._highest_tag()
        return releases[0].tag_name

    def _highest_tag(self) -> str:
        """Walk all tags and return the one with the highest all-numeric version,
        tolerating any leading non-digit prefix and underscore/hyphen separators."""
        best_tag: str | None = None
        best_version: Version | None = None
        for tag in self._project.tags.list(get_all=True):
            v = _tag_version(tag.name)
            if v is None:
                continue
            if best_version is None or v > best_version:
                best_version = v
                best_tag = tag.name
        if best_tag is None:
            raise RuntimeError(
                f"no version-like tags found for {self._slug} on {self._host}")
        return best_tag
