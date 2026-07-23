from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin

from thirdparty._internal.errors import (
    AuthenticationException,
    ForbiddenException,
    NotFoundException,
    RequestErrorException,
)
from thirdparty._internal.pack.layout import MT_INDEX, MT_MANIFEST, canonical_json


def _noop_log(msg: str) -> None:
    pass


def _read_token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise AuthenticationException(
            "GH_TOKEN or GITHUB_TOKEN must be set to publish to GHCR")
    return token


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


class GHCRClient:
    """Push an on-disk OCI layout to GHCR over the OCI Distribution (registry v2) API.

    No Docker: blobs and manifests are PUT directly with :class:`HttpRequester`.  A
    top-level multi-arch index tag accretes one platform manifest per publish, so a
    consumer pulls ``<name>:<version>`` and resolves its os/arch (Homebrew-bottle style)."""

    def __init__(
        self,
        owner: str,
        name: str,
        *,
        registry: str = "ghcr.io",
        prefix: str = "thirdparty",
        http: "Any | None" = None,
        log: "Callable[[str], None] | None" = None) -> None:
        self.registry = registry
        self.owner = owner
        self.name = name
        self.repo = f"{owner}/{prefix}/{name}" if prefix else f"{owner}/{name}"
        self._base = f"https://{registry}"
        self._http: Any = http if http is not None else _default_http()
        self._log: "Callable[[str], None]" = log if log is not None else _noop_log
        self._auth: "dict[str, str]" = {}

    # -- auth -------------------------------------------------------------------------
    def authenticate(self) -> None:
        token = _read_token()
        basic = base64.b64encode(f"{self.owner}:{token}".encode()).decode()
        resp = self._http.get(
            f"{self._base}/token",
            params={"service": self.registry, "scope": f"repository:{self.repo}:pull,push"},
            headers={"Authorization": f"Basic {basic}"})
        _raise_for_status(resp, "token exchange")
        bearer = resp.json().get("token") or resp.json().get("access_token")
        if not bearer:
            raise AuthenticationException("token exchange returned no token")
        self._auth = {"Authorization": f"Bearer {bearer}"}

    # -- blobs ------------------------------------------------------------------------
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

    # -- manifests --------------------------------------------------------------------
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

    # -- orchestration ----------------------------------------------------------------
    def push_layout(self, layout_dir: Path, tag: str, *, dry_run: bool = False) -> str:
        """Push every blob + the manifest from *layout_dir*, then merge into the ``tag`` index.

        Returns the pushed manifest digest."""
        index_doc = json.loads((layout_dir / "index.json").read_text(encoding="utf-8"))
        manifest_desc = index_doc["manifests"][0]
        manifest_digest = manifest_desc["digest"]
        platform = manifest_desc.get("platform", {})
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
            self._log(f"[dry-run]   GET+merge+PUT index tag {tag} "
                      f"(platform {platform.get('os')}/{platform.get('architecture')})")
            return manifest_digest

        self.authenticate()
        for digest in blob_digests:
            data = (blobs / digest.split(":", 1)[1]).read_bytes()
            self._push_blob(digest, data)
        self._put_manifest(manifest_digest, manifest_bytes, MT_MANIFEST)
        self._log(f"  pushed manifest {manifest_digest}")

        self._merge_index(tag, manifest_desc)
        self._log(f"  updated index {self.registry}/{self.repo}:{tag}")
        return manifest_digest

    def _merge_index(self, tag: str, manifest_desc: "dict[str, Any]") -> None:
        """Add/replace this platform's manifest in the ``tag`` index, then PUT it."""
        existing = self._get_index(tag)
        manifests: list[dict[str, Any]] = list(existing["manifests"]) if existing else []
        platform = manifest_desc.get("platform", {})
        # Replace any prior entry for the same platform (re-publish), else append.
        manifests = [
            m for m in manifests if m.get("platform") != platform]
        manifests.append(manifest_desc)
        index = {
            "schemaVersion": 2,
            "mediaType": MT_INDEX,
            "manifests": manifests,
        }
        self._put_manifest(tag, canonical_json(index), MT_INDEX)


def _default_http() -> Any:
    from thirdparty._internal.model.conf import Conf
    from thirdparty._internal.util.http_requester import HttpRequester
    return HttpRequester(Conf())
