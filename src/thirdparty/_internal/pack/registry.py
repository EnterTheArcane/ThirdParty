from __future__ import annotations

import base64
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin

from thirdparty._internal.errors import (
    AuthenticationException,
    ForbiddenException,
    NotFoundException,
    RequestErrorException,
)
from thirdparty._internal.pack.digest import oci_digest
from thirdparty._internal.pack.layout import MT_INDEX, MT_MANIFEST, canonical_json
from thirdparty._internal.pack.meta import oci_arch, oci_os


# Manifest media types we accept when reading existing manifests back from the registry.
_MANIFEST_ACCEPT = ", ".join([
    MT_MANIFEST,
    "application/vnd.docker.distribution.manifest.v2+json",
])

# When pulling we accept indexes too, so the registry returns the multi-arch index verbatim
# (we select the platform ourselves) rather than resolving a platform server-side.
_PULL_ACCEPT = ", ".join([
    MT_INDEX,
    "application/vnd.docker.distribution.manifest.list.v2+json",
    MT_MANIFEST,
    "application/vnd.docker.distribution.manifest.v2+json",
])

# Docker Hub is addressed by several host spellings; its config.json key is a legacy URL.
_DOCKERHUB_HOSTS = {"docker.io", "registry-1.docker.io", "index.docker.io"}
_DOCKERHUB_CONFIG_KEY = "https://index.docker.io/v1/"

# Multi-arch index media types (OCI + Docker manifest list).
_INDEX_TYPES = {MT_INDEX, "application/vnd.docker.distribution.manifest.list.v2+json"}


def parse_reference(uri: str) -> "tuple[str, str, str]":
    """Split an OCI reference ``[registry/]repository[:tag|@digest]`` into (registry, repository, ref).

    The first path segment is the registry host when it looks like one (contains ``.`` or ``:`` or is
    ``localhost``); the trailing ``@sha256:…`` digest or ``:tag`` (after the last ``/``) is the ref,
    defaulting to ``latest``.  E.g. ``ghcr.io/o3de/thirdparty/zlib:1.3.2`` ->
    ``("ghcr.io", "o3de/thirdparty/zlib", "1.3.2")``."""
    first, slash, rest = uri.partition("/")
    if slash and ("." in first or ":" in first or first == "localhost"):
        registry, remainder = first, rest
    else:
        registry, remainder = "docker.io", uri

    if "@" in remainder:
        repository, _, ref = remainder.partition("@")
    else:
        head, sep, tail = remainder.rpartition(":")
        if sep and "/" not in tail:
            repository, ref = head, tail
        else:
            repository, ref = remainder, "latest"
    return registry, repository, ref


def _noop_log(msg: str) -> None:
    pass


def _platform_key(platform: "dict[str, Any]") -> str:
    return f"{platform.get('os')}/{platform.get('architecture')}"


def _next_link(link_header: "str | None", base: str) -> str:
    """Extract the ``rel="next"`` URL from a registry ``Link`` header (paginated tags list)."""
    if not link_header or 'rel="next"' not in link_header:
        return ""
    start = link_header.find("<")
    end = link_header.find(">", start + 1)
    if start == -1 or end == -1:
        return ""
    return urljoin(base + "/", link_header[start + 1:end])


def _raise_for_status(resp: Any, context: str) -> None:
    code = int(resp.status_code)
    if 200 <= code < 300:
        return
    body = ""
    try:
        body = resp.text[:500]
    except Exception:
        pass
    if code == 401:
        raise AuthenticationException(f"{context}: unauthorized (401) {body}")
    if code == 403:
        raise ForbiddenException(f"{context}: forbidden (403) {body}")
    if code == 404:
        raise NotFoundException(f"{context}: not found (404)")
    raise RequestErrorException(f"{context}: HTTP {code} {body}")


@dataclass(frozen=True)
class _Credentials:
    username: str
    secret: str


@dataclass(frozen=True)
class _Challenge:
    scheme: str            # "bearer" | "basic"
    realm: str
    service: "str | None"


def _basic_header(creds: _Credentials) -> str:
    raw = f"{creds.username}:{creds.secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _parse_www_authenticate(header: "str | None") -> "_Challenge | None":
    """Parse a registry ``WWW-Authenticate`` challenge into scheme + realm/service.

    Handles ``Bearer realm="…",service="…",scope="…"`` and ``Basic realm="…"``.  The token
    *realm* can be a completely different host from the registry (Docker Hub's is
    ``auth.docker.io``), which is exactly why we discover it rather than hardcode it."""
    if not header:
        return None
    scheme, _, rest = header.strip().partition(" ")
    params = {m.group(1).lower(): m.group(2) for m in re.finditer(r'(\w+)="([^"]*)"', rest)}
    kind = scheme.lower()
    if kind == "bearer":
        realm = params.get("realm")
        if not realm:
            return None
        return _Challenge("bearer", realm, params.get("service"))
    if kind == "basic":
        return _Challenge("basic", params.get("realm", ""), None)
    return None


class OciRegistryClient:
    """Push an on-disk OCI layout to any OCI-compliant registry (registry v2 API).

    No Docker: blobs and manifests are PUT directly with :class:`HttpRequester`.  Auth is
    discovered from the registry's ``WWW-Authenticate`` challenge (Bearer token exchange, or
    Basic), so this works with GHCR, Docker Hub, GitLab, Quay, Harbor, and self-hosted
    ``registry:2`` alike.  Each publish writes a per-platform tag (``<tag>-<os>-<arch>``) and
    never touches the shared multi-arch tag; :meth:`combine_index` assembles that tag from the
    per-platform tags, so parallel CI runners never race.  A consumer then pulls
    ``<name>:<version>`` and the registry resolves its os/arch (Homebrew-bottle style)."""

    def __init__(
        self,
        owner: str,
        name: str,
        *,
        registry: str = "ghcr.io",
        prefix: str = "thirdparty",
        repository: "str | None" = None,
        username: "str | None" = None,
        password: "str | None" = None,
        http: "Any | None" = None,
        log: "Callable[[str], None] | None" = None) -> None:
        self.registry = registry
        self.owner = owner
        self.name = name
        # An explicit repository (from a full pull URI) wins; otherwise compose it from owner/prefix/name.
        self.repo = repository or (f"{owner}/{prefix}/{name}" if prefix else f"{owner}/{name}")
        self._base = f"https://{registry}"
        self._username = username
        self._password = password
        self._http: Any = http if http is not None else _default_http()
        self._log: "Callable[[str], None]" = log if log is not None else _noop_log
        self._auth: "dict[str, str]" = {}

    def authenticate(self, actions: str = "pull,push") -> None:
        """Discover and satisfy the registry's auth scheme via its ``/v2/`` challenge.

        *actions* is the requested token scope (``pull`` for read-only pulls, ``pull,push`` for
        publishing).  With no credentials a Bearer challenge still yields an anonymous token, so
        public-image pulls work credential-free."""
        resp = self._http.get(f"{self._base}/v2/", headers={})
        code = int(resp.status_code)
        if 200 <= code < 300:
            self._auth = {}  # anonymous access is allowed (reads on a public repo)
            return
        if code != 401:
            _raise_for_status(resp, "registry probe")
        challenge = _parse_www_authenticate(resp.headers.get("WWW-Authenticate"))
        if challenge is None:
            raise AuthenticationException(
                f"{self.registry} requires auth but sent no supported WWW-Authenticate challenge")
        creds = self._resolve_credentials()
        if challenge.scheme == "bearer":
            self._auth = {"Authorization": f"Bearer {self._fetch_bearer(challenge, creds, actions)}"}
        else:  # basic
            if creds is None:
                raise AuthenticationException(
                    f"{self.registry} requires credentials (Basic auth); none found")
            self._auth = {"Authorization": _basic_header(creds)}

    def _fetch_bearer(
        self, challenge: _Challenge, creds: "_Credentials | None", actions: str = "pull,push") -> str:
        params: dict[str, str] = {"scope": f"repository:{self.repo}:{actions}"}
        if challenge.service:
            params["service"] = challenge.service
        # No credentials -> no Authorization header -> the registry issues an anonymous token
        # (public pulls). Credentials, when present, authorize a scoped (e.g. push-capable) token.
        headers = {"Authorization": _basic_header(creds)} if creds is not None else {}
        resp = self._http.get(challenge.realm, params=params, headers=headers)
        _raise_for_status(resp, "token exchange")
        body: Any = resp.json()
        token = None
        if isinstance(body, dict):
            body_dict = cast("dict[str, Any]", body)
            token = body_dict.get("token") or body_dict.get("access_token")
        if not token:
            raise AuthenticationException("token exchange returned no token")
        return str(token)

    def _resolve_credentials(self) -> "_Credentials | None":
        """Credentials for *this* registry, first match wins:

        1. explicit ``--username``/``--password`` flags;
        2. ``GH_TOKEN``/``GITHUB_TOKEN`` for ghcr.io (zero-config default);
        3. ``REGISTRY_USERNAME`` + ``REGISTRY_PASSWORD``/``REGISTRY_TOKEN``;
        4. ``~/.docker/config.json`` static ``auths`` (an existing ``docker login``);
        5. ``~/.netrc``; else anonymous."""
        if self._username or self._password:
            return _Credentials(self._username or "", self._password or "")

        if self.registry.endswith("ghcr.io"):
            gh = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
            if gh:
                return _Credentials(self.owner, gh)

        env_user = os.environ.get("REGISTRY_USERNAME")
        env_secret = os.environ.get("REGISTRY_PASSWORD") or os.environ.get("REGISTRY_TOKEN")
        if env_user or env_secret:
            return _Credentials(env_user or self.owner, env_secret or "")

        creds = self._docker_config_credentials()
        if creds is not None:
            return creds

        return self._netrc_credentials()

    def _docker_config_credentials(self) -> "_Credentials | None":
        config_dir = os.environ.get("DOCKER_CONFIG") or os.path.join(
            os.path.expanduser("~"), ".docker")
        path = Path(config_dir) / "config.json"
        if not path.exists():
            return None
        try:
            data = cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

        auths = cast("dict[str, Any]", data.get("auths") or {})
        keys = [self.registry]
        if self.registry in _DOCKERHUB_HOSTS:
            keys += [_DOCKERHUB_CONFIG_KEY, *_DOCKERHUB_HOSTS]
        entry: "dict[str, Any] | None" = None
        for key in keys:
            if key in auths:
                entry = cast("dict[str, Any]", auths[key])
                break
        if entry is None:
            for key, value in auths.items():
                if self.registry in key:
                    entry = cast("dict[str, Any]", value)
                    break
        if entry is None:
            # credHelpers/credsStore shell out to docker-credential-* binaries, which we do not
            # run (no external tools). Point the user at an alternative if that is all they have.
            if data.get("credsStore") or (cast("dict[str, Any]", data.get("credHelpers") or {})).get(self.registry):
                self._log(f"  note: {self.registry} uses a docker credential helper "
                          "(unsupported); pass --username/--password or set REGISTRY_* env")
            return None

        encoded = entry.get("auth")
        if encoded:
            try:
                user, _, secret = base64.b64decode(encoded).decode("utf-8").partition(":")
            except Exception:
                user, secret = "", ""
            if user or secret:
                return _Credentials(user, secret)
        user = entry.get("username")
        secret = entry.get("password")
        if user or secret:
            return _Credentials(str(user or ""), str(secret or ""))
        return None

    def _netrc_credentials(self) -> "_Credentials | None":
        import netrc
        try:
            auth = netrc.netrc().authenticators(self.registry)
        except Exception:
            return None
        if not auth:
            return None
        login, _account, password = auth
        if login or password:
            return _Credentials(login or "", password or "")
        return None

    def _blob_exists(self, digest: str) -> bool:
        resp = self._http.head(
            f"{self._base}/v2/{self.repo}/blobs/{digest}", headers=dict(self._auth))
        code = int(resp.status_code)
        if code == 200:
            return True
        if code == 404:
            return False
        _raise_for_status(resp, f"blob head {digest}")
        return False

    def _push_blob(self, digest: str, data: bytes) -> None:
        if self._blob_exists(digest):
            self._log(f"  blob {digest[:19]} already present")
            return
        start = self._http.post(
            f"{self._base}/v2/{self.repo}/blobs/uploads/", headers=dict(self._auth))
        _raise_for_status(start, "blob upload start")
        location = start.headers.get("Location")
        if not location:
            raise RequestErrorException("blob upload start returned no Location header")
        upload_url = urljoin(f"{self._base}/", location)
        sep = "&" if "?" in upload_url else "?"
        put_url = f"{upload_url}{sep}digest={digest}"
        headers = {**self._auth, "Content-Type": "application/octet-stream"}
        resp = self._http.put(put_url, headers=headers, data=data)
        _raise_for_status(resp, f"blob upload {digest}")
        self._log(f"  pushed blob {digest[:19]} ({len(data)} bytes)")

    def _put_manifest(self, reference: str, data: bytes, media_type: str) -> None:
        headers = {**self._auth, "Content-Type": media_type}
        resp = self._http.put(
            f"{self._base}/v2/{self.repo}/manifests/{reference}", headers=headers, data=data)
        _raise_for_status(resp, f"manifest put {reference}")

    def _get_index(self, tag: str) -> "dict[str, Any] | None":
        resp = self._http.get(
            f"{self._base}/v2/{self.repo}/manifests/{tag}",
            headers={**self._auth, "Accept": MT_INDEX})
        code = int(resp.status_code)
        if code == 404:
            return None
        _raise_for_status(resp, f"index get {tag}")
        try:
            doc: Any = resp.json()
        except Exception:
            return None
        if isinstance(doc, dict):
            result = cast("dict[str, Any]", doc)
            if result.get("mediaType") == MT_INDEX:
                return result
        return None

    def _list_tags(self) -> "list[str]":
        """All tags in the repository (following pagination); empty if the repo is new."""
        url: str = f"{self._base}/v2/{self.repo}/tags/list"
        tags: list[str] = []
        first = True
        for _ in range(50):  # hard page cap - a runaway backstop, not a real limit
            kwargs: dict[str, Any] = {"headers": {**self._auth, "Accept": "application/json"}}
            if first:
                kwargs["params"] = {"n": 500}
            resp = self._http.get(url, **kwargs)
            if int(resp.status_code) == 404:
                return tags
            _raise_for_status(resp, "tags list")
            body: Any = resp.json()
            if isinstance(body, dict):
                body_dict = cast("dict[str, Any]", body)
                tags.extend(cast("list[str]", body_dict.get("tags") or []))
            nxt = _next_link(resp.headers.get("Link"), self._base)
            if not nxt:
                break
            url, first = nxt, False
        return tags

    def _get_manifest(
        self, reference: str, accept: str = _MANIFEST_ACCEPT) -> "tuple[bytes, str, dict[str, Any]]":
        """Fetch a manifest by tag/digest: returns (raw bytes, content digest, parsed doc)."""
        resp = self._http.get(
            f"{self._base}/v2/{self.repo}/manifests/{reference}",
            headers={**self._auth, "Accept": accept})
        _raise_for_status(resp, f"manifest get {reference}")
        content: bytes = resp.content
        digest = resp.headers.get("Docker-Content-Digest") or oci_digest(content)
        doc = cast("dict[str, Any]", json.loads(content))
        return content, digest, doc

    def _download_blob(self, digest: str, dest_path: Path) -> None:
        """Stream a blob to *dest_path* (must not pre-exist) and verify its sha256 digest."""
        from thirdparty._internal.util.file_downloader import FileDownloader
        url = f"{self._base}/v2/{self.repo}/blobs/{digest}"
        hex_digest = digest.split(":", 1)[1] if ":" in digest else digest
        FileDownloader(self._http, scope="oci-pull").download(
            url, str(dest_path.resolve()), headers=dict(self._auth), sha256=hex_digest)

    def resolve_platform_manifest(
        self, reference: str, want_platform: str) -> "tuple[dict[str, Any], str]":
        """Resolve *reference* to a single image manifest for *want_platform* (``os/arch``).

        If the reference is a multi-arch index, select the entry whose OCI platform matches; raise
        :class:`NotFoundException` (listing available platforms) if none do.  A plain image manifest
        is returned as-is.  Returns (image-manifest doc, its digest)."""
        _content, digest, doc = self._get_manifest(reference, accept=_PULL_ACCEPT)
        is_index = doc.get("mediaType") in _INDEX_TYPES or (
            "manifests" in doc and "layers" not in doc)
        if not is_index:
            return doc, digest

        want_os, _, want_arch = want_platform.partition("/")
        available: list[str] = []
        for entry in cast("list[dict[str, Any]]", doc.get("manifests") or []):
            plat = cast("dict[str, Any]", entry.get("platform") or {})
            available.append(f"{plat.get('os')}/{plat.get('architecture')}")
            if plat.get("os") == want_os and plat.get("architecture") == want_arch:
                _c, mdigest, mdoc = self._get_manifest(entry["digest"], accept=_PULL_ACCEPT)
                return mdoc, mdigest
        raise NotFoundException(
            f"{self.repo}: no image for platform '{want_platform}'; "
            f"available: {', '.join(sorted(set(available))) or 'none'}")

    def pull_extract(
        self, reference: str, dest: Path, want_platform: str, *,
        dry_run: bool = False) -> "dict[str, Any]":
        """Pull *reference* for *want_platform* and extract its layer(s) into *dest*.

        Anonymous-capable (public images need no credentials).  Extraction uses the safe ``data``
        tar filter.  Writes a ``.thirdparty-oci.json`` sidecar with the os/arch/version annotations
        for the package system.  Returns {platform, digest, layers}."""
        import tempfile
        from thirdparty.files.files import untargz

        self.authenticate("pull")
        doc, digest = self.resolve_platform_manifest(reference, want_platform)
        layers = cast("list[dict[str, Any]]", doc.get("layers") or [])
        result: dict[str, Any] = {
            "platform": want_platform, "digest": digest,
            "layers": [str(layer["digest"]) for layer in layers]}

        if dry_run:
            self._log(f"[dry-run] would pull {self.registry}/{self.repo}@{digest} ({want_platform})")
            for layer in layers:
                self._log(f"[dry-run]   download + extract layer {layer['digest']}")
            return result

        dest.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            for i, layer in enumerate(layers):
                blob_path = Path(tmp) / f"layer{i}"
                self._download_blob(str(layer["digest"]), blob_path)
                untargz(str(blob_path), dest, extract_filter="data")
                self._log(f"  extracted layer {str(layer['digest'])[:19]} -> {dest}")
        self._write_pull_metadata(dest, doc, digest, want_platform)
        return result

    def _write_pull_metadata(
        self, dest: Path, doc: "dict[str, Any]", digest: str, want_platform: str) -> None:
        ann = cast("dict[str, Any]", doc.get("annotations") or {})
        meta = {k: v for k, v in ann.items() if k.startswith("io.o3de.thirdparty.")}
        meta["platform"] = want_platform
        meta["manifest_digest"] = digest
        (dest / ".thirdparty-oci.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")

    def platform_tag(self, tag: str, manifest_desc: "dict[str, Any]") -> str:
        """Per-platform tag, e.g. ``1.3.2-mac-arm`` - a stable, collision-free handle each CI
        runner can push in parallel without racing on the shared multi-arch tag.

        Uses the thirdparty ``package_id`` (O3DE ``<os>-<arch>`` naming, e.g. ``mac-arm``) from the
        manifest's annotations so registry tags match the rest of the build system; falls back to the
        OCI platform (``darwin-arm64``) for images that don't carry that annotation."""
        ann = cast("dict[str, Any]", manifest_desc.get("annotations") or {})
        package_id = ann.get("io.o3de.thirdparty.package_id")
        if package_id:
            return f"{tag}-{package_id}"
        platform = cast("dict[str, Any]", manifest_desc.get("platform") or {})
        return f"{tag}-{platform.get('os')}-{platform.get('architecture')}"

    def push_layout(self, layout_dir: Path, tag: str, *, dry_run: bool = False) -> str:
        """Push every blob + the manifest from *layout_dir* under the per-platform tag
        ``<tag>-<package_id>`` (e.g. ``1.3.2-mac-arm``).

        Never touches the shared multi-arch ``tag`` - that is assembled separately by
        :meth:`combine_index`, so parallel runners never race.  Returns the pushed manifest
        digest."""
        index_doc = json.loads((layout_dir / "index.json").read_text(encoding="utf-8"))
        manifest_desc = index_doc["manifests"][0]
        manifest_digest = manifest_desc["digest"]
        plat_tag = self.platform_tag(tag, manifest_desc)
        blobs = layout_dir / "blobs" / "sha256"

        manifest_bytes = (blobs / manifest_digest.split(":", 1)[1]).read_bytes()
        manifest = json.loads(manifest_bytes)
        blob_digests = [manifest["config"]["digest"]] + [
            layer["digest"] for layer in manifest["layers"]]

        if dry_run:
            self._log(f"[dry-run] would push to {self.registry}/{self.repo}")
            for digest in blob_digests:
                self._log(f"[dry-run]   HEAD/POST/PUT blob {digest}")
            self._log(f"[dry-run]   PUT manifest {manifest_digest}")
            self._log(f"[dry-run]   PUT per-platform tag {plat_tag}")
            return manifest_digest

        self.authenticate()
        for digest in blob_digests:
            data = (blobs / digest.split(":", 1)[1]).read_bytes()
            self._push_blob(digest, data)
        self._put_manifest(manifest_digest, manifest_bytes, MT_MANIFEST)
        self._log(f"  pushed manifest {manifest_digest}")
        self._put_manifest(plat_tag, manifest_bytes, MT_MANIFEST)
        self._log(f"  tagged {self.registry}/{self.repo}:{plat_tag}")
        return manifest_digest

    def combine_index(self, tag: str, *, dry_run: bool = False) -> "list[dict[str, Any]]":
        """Assemble/upsert the multi-arch ``tag`` index from every ``<tag>-<os>-<arch>`` tag.

        Additive and idempotent: starts from the existing index (preserving platforms), then
        upserts one entry per per-platform tag currently in the registry (replacing an entry
        for the same platform).  Re-running the pipeline for just one OS/arch refreshes that
        platform and leaves the rest intact.  Returns the resulting manifest descriptors."""
        self.authenticate()
        by_platform: dict[str, dict[str, Any]] = {}

        existing = self._get_index(tag)
        if existing:
            for desc in cast("list[dict[str, Any]]", existing.get("manifests", [])):
                by_platform[_platform_key(desc.get("platform", {}))] = desc

        prefix = f"{tag}-"
        for candidate in self._list_tags():
            if candidate == tag or not candidate.startswith(prefix):
                continue
            content, digest, doc = self._get_manifest(candidate)
            if doc.get("mediaType") == MT_INDEX:
                continue  # skip a nested index that happens to share the prefix
            ann: dict[str, Any] = doc.get("annotations") or {}
            os_name = ann.get("io.o3de.thirdparty.os")
            arch = ann.get("io.o3de.thirdparty.arch")
            if not os_name or not arch:
                self._log(f"  skip {candidate}: no platform annotations")
                continue
            platform = {"architecture": oci_arch(arch), "os": oci_os(os_name)}
            desc: dict[str, Any] = {
                "mediaType": MT_MANIFEST,
                "digest": digest,
                "size": len(content),
                "platform": platform,
                "annotations": {
                    "org.opencontainers.image.ref.name": tag,
                    "io.o3de.thirdparty.package_id": ann.get("io.o3de.thirdparty.package_id", ""),
                },
            }
            by_platform[_platform_key(platform)] = desc

        manifests = [by_platform[key] for key in sorted(by_platform)]
        if dry_run:
            self._log(f"[dry-run] would PUT index {self.registry}/{self.repo}:{tag} "
                      f"with platforms: {[_platform_key(m['platform']) for m in manifests]}")
            return manifests
        index = {"schemaVersion": 2, "mediaType": MT_INDEX, "manifests": manifests}
        self._put_manifest(tag, canonical_json(index), MT_INDEX)
        self._log(f"  combined index {self.registry}/{self.repo}:{tag} "
                  f"({len(manifests)} platform(s))")
        return manifests


def _default_http() -> Any:
    from thirdparty._internal.model.conf import Conf
    from thirdparty._internal.util.http_requester import HttpRequester
    return HttpRequester(Conf())
