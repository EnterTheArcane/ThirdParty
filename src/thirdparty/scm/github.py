import os
import re
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable
from functools import cached_property, lru_cache
from urllib.parse import quote, unquote

import requests
from github import Auth, Github
from github.GithubException import GithubException
from github.Repository import Repository

from thirdparty._internal.model.version import Version
from thirdparty.recipe import RecipeBase


_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_HTTP_HEADERS = {"User-Agent": "thirdparty-outdated"}
_API_FALLBACK_STATUSES = {401, 403, 429}


@lru_cache(maxsize=None)
def _github_client(token: str) -> Github:
    """Share the authenticated client and do not let PyGithub sleep on API failures."""
    return Github(
        auth=Auth.Token(token),
        user_agent="thirdparty-outdated",
        per_page=100,
        retry=0)


@lru_cache(maxsize=None)
def _remote_tags(slug: str) -> tuple[str, ...]:
    """List public GitHub tags through Git's smart transport, not the rate-limited REST API."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--refs", "--tags", f"https://github.com/{slug}.git"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"unable to list tags for {slug}: {exc}") from exc

    tags: list[str] = []
    for line in result.stdout.splitlines():
        _, separator, ref = line.partition("\t")
        if separator and ref.startswith("refs/tags/"):
            tags.append(ref.removeprefix("refs/tags/"))
    return tuple(tags)


@lru_cache(maxsize=None)
def _latest_release_tag(slug: str) -> str | None:
    """Resolve GitHub's public latest-release redirect without consuming API quota."""
    response = requests.head(
        f"https://github.com/{slug}/releases/latest",
        allow_redirects=True,
        headers=_HTTP_HEADERS,
        timeout=30)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    marker = "/releases/tag/"
    if marker not in response.url:
        if response.url.rstrip("/").endswith("/releases"):
            return None
        raise RuntimeError(f"unexpected latest-release URL for {slug}: {response.url}")
    return unquote(response.url.split(marker, 1)[1])


@lru_cache(maxsize=None)
def _release_feed_tags(slug: str) -> tuple[str, ...]:
    """Return release tags in publication order from GitHub's public Atom feed."""
    response = requests.get(
        f"https://github.com/{slug}/releases.atom",
        headers=_HTTP_HEADERS,
        timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    tags: list[str] = []
    marker = "/releases/tag/"
    for entry in root.findall("atom:entry", _ATOM_NS):
        link = entry.find("atom:link[@rel='alternate']", _ATOM_NS)
        href = link.get("href", "") if link is not None else ""
        if marker in href:
            tags.append(unquote(href.split(marker, 1)[1]))
    return tuple(tags)


def _is_prerelease_tag(tag: str) -> bool:
    return re.search(
        r"(?:^|[-_.])(?:alpha|beta|preview|pre|rc)(?:[-_.]?\d|[-_.]|$)",
        tag,
        flags=re.IGNORECASE) is not None


def _tag_version(tag: str) -> Version | None:
    # Strip a leading identifier+separator prefix: "vulkan-sdk-", "nasm-", "m4-",
    # "bzip2-", "VER-", etc.  The pattern allows digits inside the word (like m4).
    stripped = re.sub(r"^(?:[A-Za-z][A-Za-z0-9]*[-_])+", "", tag)
    if not stripped or not stripped[0].isdigit():
        # Fall back to a bare single-letter prefix: v1.2, V3.4, n8.1
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
    # Require at least two components; single numbers (r42, v114, draft-15) are not versions.
    if len(v.main) < 2:
        return None
    main = [int(i.value) for i in v.main]
    # When a non-digit prefix was stripped, reject year-like first components
    # (e.g. "before-reformat-2005-01" -> 2005.01, "CVE-2021-3541" -> 2021.3541).
    if had_prefix and main[0] >= 1000:
        return None
    # Reject digit-starting YYYY-MM-DD style date tags (e.g. "2021-01-15").
    if (not had_prefix and len(main) == 3 and main[0] > 1970 and 1 <= main[1] <= 12 and 1 <= main[2] <= 31):
        return None
    return v


class GithubRepository:
    """Typed wrapper around a single GitHub repository, used by recipes.

    Usage:
        repo = GithubRepository(self, "abseil/abseil-cpp")
        repo.latest_release   # raw tag_name string, e.g. "20240722.0" or "v1.2.3"

    When GH_TOKEN or GITHUB_TOKEN is set, authenticated API requests are used for
    release and commit metadata. Git's tag transport avoids spending API quota on
    large tag collections. Public redirects and Atom feeds provide an anonymous
    fallback, including when an authenticated token is rate-limited.
    """

    def __init__(self, recipe: RecipeBase, slug: str) -> None:
        self._recipe = recipe
        self._slug = slug
        self._token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or None

    @cached_property
    def _repo(self) -> Repository:
        if self._token is None:
            raise RuntimeError("an authenticated GitHub repository was requested without a token")
        return _github_client(self._token).get_repo(self._slug)

    @cached_property
    def _tags(self) -> tuple[str, ...]:
        return _remote_tags(self._slug)

    @cached_property
    def latest_release(self) -> str:
        """Raw tag_name of the latest GitHub release.

        Resolves GitHub's latest-release redirect, then validates it against
        _highest_tag(): some repos have maintenance-branch security patches
        marked as the GitHub "Latest Release" even though newer major versions
        exist (e.g. CPython 3.9.x published after 3.13.x), or the latest
        release uses an unexpected tag scheme.  When _highest_tag() returns a
        strictly higher version, that tag is preferred.
        """
        release_tag = self._formal_release_tag()
        if release_tag is None:
            return self._highest_tag()
        try:
            ht = self._highest_tag()
            r_v = _tag_version(release_tag)
            h_v = _tag_version(ht)
            if h_v is not None and (r_v is None or h_v >= r_v):
                return ht
        except Exception:
            pass
        return release_tag

    @cached_property
    def latest_formal_release(self) -> str:
        """Raw tag_name of the GitHub latest release; no fallback to tag scanning."""
        release_tag = self._formal_release_tag()
        return release_tag if release_tag is not None else self._highest_tag()

    def latest_tag(self, prefix: str) -> str:
        """Return the raw tag name with the highest version among tags starting with `prefix`.

        Underscore-separated versions are normalised before comparison. Hyphenated
        prerelease suffixes are preserved so a final release sorts after its
        prereleases, and numeric qualifier suffixes sort naturally.
        """
        best_tag: str | None = None
        best_version: Version | None = None
        for tag in self._tags:
            if not tag.startswith(prefix):
                continue
            try:
                candidate = tag[len(prefix):].replace("_", ".")
                candidate = re.sub(r"-([A-Za-z]+)(\d+)$", r"-\1.\2", candidate)
                v = Version(candidate)
            except Exception:
                continue
            if not v.main or not all(isinstance(item.value, int) for item in v.main):
                continue
            if best_version is None or v > best_version:
                best_version = v
                best_tag = tag
        if best_tag is None:
            raise RuntimeError(f"no tag with prefix {prefix!r} found in {self._slug}")
        return best_tag

    def latest_tag_matching(
            self,
            pattern: str,
            group: int | str = 1,
            version_transform: Callable[[str], str] | None = None) -> str:
        """Return the version captured by *group* from the highest matching tag.

        This is intended for repositories whose tags contain more than a simple
        prefix, for example ``107.3-physx-5.6.1`` or
        ``release/metal-cpp_macOS27_iOS27``. ``version_transform`` can normalize
        a captured value for comparison without changing the returned value.
        """
        rx = re.compile(pattern)
        best_value: str | None = None
        best_version: Version | None = None
        for tag in self._tags:
            match = rx.fullmatch(tag)
            if match is None:
                continue
            value = match.group(group)
            try:
                version = Version(version_transform(value) if version_transform else value)
            except Exception:
                continue
            if version.pre is not None:
                continue
            if best_version is None or version > best_version:
                best_version = version
                best_value = value
        if best_value is None:
            raise RuntimeError(f"no tag matching {pattern!r} found in {self._slug}")
        return best_value

    def latest_commit_date(self, branch: str | None = None) -> str:
        """Return the newest commit date on *branch* as ``YYYYMMDD``."""
        if self._token is not None:
            try:
                commits = self._repo.get_commits(sha=branch) if branch else self._repo.get_commits()
                commit = commits[0]
                committed_at = commit.commit.committer.date
                return committed_at.strftime("%Y%m%d")
            except GithubException as exc:
                if exc.status not in _API_FALLBACK_STATUSES:
                    raise

        suffix = f"/{quote(branch, safe='')}" if branch else ""
        response = requests.get(
            f"https://github.com/{self._slug}/commits{suffix}.atom",
            headers=_HTTP_HEADERS,
            timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        entry = root.find("atom:entry", _ATOM_NS)
        updated = entry.findtext("atom:updated", namespaces=_ATOM_NS) if entry is not None else None
        if not updated:
            ref = branch or "the default branch"
            raise RuntimeError(f"no commits on {ref!r} for {self._slug}")
        return updated[:10].replace("-", "")

    def latest_release_matching(self, pattern: str) -> str:
        """Return the tag of the most recently published non-pre-release release
        whose tag_name matches the given regex pattern."""
        rx = re.compile(pattern)
        if self._token is not None:
            try:
                for release in self._repo.get_releases():
                    if not release.prerelease and rx.match(release.tag_name):
                        return release.tag_name
            except GithubException as exc:
                if exc.status not in _API_FALLBACK_STATUSES:
                    raise

        for tag in _release_feed_tags(self._slug):
            if not _is_prerelease_tag(tag) and rx.match(tag):
                return tag
        raise RuntimeError(f"no release matching {pattern!r} found in {self._slug}")

    def _formal_release_tag(self) -> str | None:
        if self._token is not None:
            try:
                return self._repo.get_latest_release().tag_name
            except GithubException as exc:
                if exc.status == 404:
                    return None
                if exc.status not in _API_FALLBACK_STATUSES:
                    raise
        return _latest_release_tag(self._slug)

    def _highest_tag(self) -> str:
        """Return the highest version-like tag advertised by Git transport."""
        best_tag: str | None = None
        best_version: Version | None = None
        for tag in self._tags:
            v = _tag_version(tag)
            if v is None:
                continue
            if best_version is None or v > best_version:
                best_version = v
                best_tag = tag
        if best_tag is None:
            raise RuntimeError(f"no version-like tags found for {self._slug}")
        return best_tag
