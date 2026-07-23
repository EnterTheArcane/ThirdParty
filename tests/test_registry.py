import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty._internal.errors import AuthenticationException
from thirdparty._internal.pack.digest import oci_digest
from thirdparty._internal.pack.layout import MT_INDEX
from thirdparty._internal.pack.meta import PackageMeta
from thirdparty._internal.pack.oci import OciBackend
from thirdparty._internal.pack.registry import OciRegistryClient

_BEARER_REALM = "https://auth.example.test/token"
_DEFAULT_CHALLENGE = f'Bearer realm="{_BEARER_REALM}",service="example.test"'


class _FakeResponse:
    def __init__(self, status_code: int, *, content: bytes = b"",
                 json_body: "Any" = None, headers: "dict[str, str] | None" = None) -> None:
        self.status_code = status_code
        self.content = content
        self._json = json_body
        self.headers = headers or {}
        self.text = json.dumps(json_body) if json_body is not None else content.decode("utf-8", "replace")

    def json(self) -> "Any":
        return self._json


class _FakeRegistry:
    """A minimal in-memory OCI registry: challenge on /v2/, stores manifests, records calls."""

    def __init__(self, *, challenge: "str | None" = _DEFAULT_CHALLENGE) -> None:
        self.calls: list[tuple[str, str]] = []
        self.seen_auth: list[tuple[str, str | None]] = []   # (url, Authorization header)
        self.store: dict[str, bytes] = {}   # ref (tag or digest) -> manifest bytes
        self.tags: set[str] = set()
        self.challenge = challenge          # None => /v2/ returns 200 (anonymous)

    def index(self, tag: str) -> "dict[str, Any] | None":
        data = self.store.get(tag)
        if data is None:
            return None
        doc = json.loads(data)
        return doc if doc.get("mediaType") == MT_INDEX else None

    def platforms(self, tag: str) -> "list[tuple[str, str]]":
        idx = self.index(tag)
        if not idx:
            return []
        return sorted((m["platform"]["os"], m["platform"]["architecture"]) for m in idx["manifests"])

    def _record(self, method: str, url: str, kwargs: "dict[str, Any]") -> None:
        self.calls.append((method, url))
        headers: "dict[str, str]" = kwargs.get("headers") or {}
        self.seen_auth.append((url, headers.get("Authorization")))

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self._record("GET", url, kwargs)
        if url.endswith("/v2/"):
            if self.challenge is None:
                return _FakeResponse(200, json_body={})
            return _FakeResponse(401, headers={"WWW-Authenticate": self.challenge})
        if url.endswith("/token"):
            return _FakeResponse(200, json_body={"token": "fake-bearer"})
        if url.endswith("/tags/list"):
            return _FakeResponse(200, json_body={"tags": sorted(self.tags)})
        if "/manifests/" in url:
            ref = url.split("/manifests/", 1)[1]
            data = self.store.get(ref)
            if data is None:
                return _FakeResponse(404)
            return _FakeResponse(
                200, content=data, json_body=json.loads(data),
                headers={"Docker-Content-Digest": oci_digest(data)})
        return _FakeResponse(404)

    def head(self, url: str, **kwargs: Any) -> _FakeResponse:
        self._record("HEAD", url, kwargs)
        return _FakeResponse(404)  # force blob upload

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self._record("POST", url, kwargs)
        return _FakeResponse(202, headers={"Location": url + "upload-id"})

    def put(self, url: str, **kwargs: Any) -> _FakeResponse:
        self._record("PUT", url, kwargs)
        if "/manifests/" in url:
            ref = url.split("/manifests/", 1)[1]
            self.store[ref] = kwargs["data"]
            if not ref.startswith("sha256:"):
                self.tags.add(ref)
        return _FakeResponse(201)


def _meta(os_name: str, arch: str, package_id: str) -> PackageMeta:
    return PackageMeta(
        name="zlib", version="1.3.2", package_id=package_id,
        os=os_name, arch=arch, build_type="Release")


def _layout(tmp: Path, meta: PackageMeta, sub: str, *, payload: bytes = b"BIN") -> Path:
    staged = tmp / sub / "package"
    (staged / "lib").mkdir(parents=True)
    (staged / "lib" / "z.lib").write_bytes(payload)
    out = tmp / sub / "oci"
    OciBackend().pack(staged, out, meta)
    return out


def _client(reg: _FakeRegistry, **kwargs: Any) -> OciRegistryClient:
    return OciRegistryClient("o3de", "zlib", http=reg, **kwargs)


class PublishTests(unittest.TestCase):
    def test_push_writes_per_platform_tag_not_the_shared_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _layout(Path(tmp), _meta("Windows", "X64", "windows-x64"), "win")
            reg = _FakeRegistry()
            with patch.dict("os.environ", {"GH_TOKEN": "t"}, clear=False):
                _client(reg).push_layout(layout, "1.3.2")

            methods = [m for m, _ in reg.calls]
            self.assertTrue(reg.calls[0][1].endswith("/v2/"))  # challenge probe first
            self.assertEqual(methods.count("HEAD"), 2)   # config + layer blob checks
            self.assertEqual(methods.count("POST"), 2)   # config + layer uploads
            # only the per-platform tag is written; the shared multi-arch tag is never touched
            self.assertIn("1.3.2-windows-amd64", reg.tags)
            self.assertIsNone(reg.index("1.3.2"))

    def test_bearer_challenge_is_discovered_from_realm_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _layout(Path(tmp), _meta("Windows", "X64", "windows-x64"), "win")
            reg = _FakeRegistry()  # realm on auth.example.test, NOT the registry host
            with patch.dict("os.environ", {"GH_TOKEN": "t"}, clear=False):
                _client(reg).push_layout(layout, "1.3.2")

            # the token was fetched from the challenge realm, not <registry>/token
            token_gets = [u for m, u in reg.calls if m == "GET" and u.startswith(_BEARER_REALM)]
            self.assertEqual(len(token_gets), 1)
            self.assertFalse(any(u == "https://ghcr.io/token" for _, u in reg.calls))
            # every write after auth carries the discovered Bearer token
            put_auth = [a for u, a in reg.seen_auth if "/manifests/" in u or "digest=" in u]
            self.assertTrue(put_auth and all(a == "Bearer fake-bearer" for a in put_auth))

    def test_basic_auth_registry_uses_basic_no_token_exchange(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _layout(Path(tmp), _meta("Windows", "X64", "windows-x64"), "win")
            reg = _FakeRegistry(challenge='Basic realm="registry"')
            client = _client(reg, registry="registry.internal", username="u", password="p")
            client.push_layout(layout, "1.3.2")

            self.assertFalse(any(u.endswith("/token") for _, u in reg.calls))  # no token exchange
            expected = "Basic " + base64.b64encode(b"u:p").decode()
            put_auth = [a for u, a in reg.seen_auth if "/manifests/" in u]
            self.assertTrue(put_auth and all(a == expected for a in put_auth))

    def test_basic_auth_without_credentials_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _layout(Path(tmp), _meta("Windows", "X64", "windows-x64"), "win")
            reg = _FakeRegistry(challenge='Basic realm="registry"')
            client = _client(reg, registry="registry.internal")
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(AuthenticationException):
                    client.push_layout(layout, "1.3.2")

    def test_anonymous_when_v2_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            _layout(Path(tmp), _meta("Windows", "X64", "windows-x64"), "win")
            reg = _FakeRegistry(challenge=None)  # /v2/ returns 200 -> anonymous
            client = _client(reg, registry="public.internal")
            with patch.dict("os.environ", {}, clear=True):
                client.combine_index("1.3.2")  # reads only (empty repo)
            self.assertTrue(all(a is None for _, a in reg.seen_auth))  # no Authorization sent

    def test_combine_assembles_index_from_per_platform_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            win = _layout(Path(tmp), _meta("Windows", "X64", "windows-x64"), "win")
            lin = _layout(Path(tmp), _meta("Linux", "ARM", "linux-arm"), "lin")
            reg = _FakeRegistry()
            with patch.dict("os.environ", {"GH_TOKEN": "t"}, clear=False):
                client = _client(reg)
                client.push_layout(win, "1.3.2")
                client.push_layout(lin, "1.3.2")
                client.combine_index("1.3.2")
            self.assertEqual(
                reg.platforms("1.3.2"), [("linux", "arm64"), ("windows", "amd64")])

    def test_combine_is_additive_upsert_on_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reg = _FakeRegistry()
            with patch.dict("os.environ", {"GH_TOKEN": "t"}, clear=False):
                client = _client(reg)
                client.push_layout(
                    _layout(root, _meta("Windows", "X64", "windows-x64"), "win"), "1.3.2")
                client.push_layout(
                    _layout(root, _meta("Linux", "ARM", "linux-arm"), "lin"), "1.3.2")
                client.combine_index("1.3.2")
                self.assertEqual(len(reg.index("1.3.2")["manifests"]), 2)

                # Rerun for ONLY android: push its per-platform tag, then combine again.
                client.push_layout(
                    _layout(root, _meta("Android", "ARM", "android-arm"), "and"), "1.3.2")
                client.combine_index("1.3.2")

            self.assertEqual(
                reg.platforms("1.3.2"),
                [("android", "arm64"), ("linux", "arm64"), ("windows", "amd64")])

    def test_combine_refreshes_digest_for_rebuilt_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reg = _FakeRegistry()
            meta = _meta("Android", "ARM", "android-arm")
            with patch.dict("os.environ", {"GH_TOKEN": "t"}, clear=False):
                client = _client(reg)
                client.push_layout(_layout(root, meta, "a1", payload=b"OLD"), "1.3.2")
                client.combine_index("1.3.2")
                first = reg.index("1.3.2")["manifests"][0]["digest"]
                client.push_layout(_layout(root, meta, "a2", payload=b"NEW-CONTENT"), "1.3.2")
                client.combine_index("1.3.2")
                second = reg.index("1.3.2")["manifests"][0]["digest"]
            self.assertEqual(len(reg.index("1.3.2")["manifests"]), 1)
            self.assertNotEqual(first, second)

    def test_dry_run_push_makes_no_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _layout(Path(tmp), _meta("Windows", "X64", "windows-x64"), "win")
            reg = _FakeRegistry()
            digest = _client(reg).push_layout(layout, "1.3.2", dry_run=True)
            self.assertEqual(reg.calls, [])
            self.assertTrue(digest.startswith("sha256:"))


class CredentialResolutionTests(unittest.TestCase):
    def _client(self, registry: str, **kwargs: Any) -> OciRegistryClient:
        return OciRegistryClient("o3de", "zlib", registry=registry, http=_FakeRegistry(), **kwargs)

    def test_flags_win(self):
        with patch.dict("os.environ", {"GH_TOKEN": "envtok"}, clear=True):
            creds = self._client("ghcr.io", username="flaguser", password="flagpass")._resolve_credentials()
        assert creds is not None
        self.assertEqual((creds.username, creds.secret), ("flaguser", "flagpass"))

    def test_ghcr_uses_gh_token(self):
        with patch.dict("os.environ", {"GH_TOKEN": "envtok"}, clear=True):
            creds = self._client("ghcr.io")._resolve_credentials()
        assert creds is not None
        self.assertEqual((creds.username, creds.secret), ("o3de", "envtok"))

    def test_docker_config_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.json"
            auth = base64.b64encode(b"dockeruser:dockerpass").decode()
            cfg.write_text(json.dumps({"auths": {"myreg.io": {"auth": auth}}}), encoding="utf-8")
            with patch.dict("os.environ", {"DOCKER_CONFIG": tmp}, clear=True):
                creds = self._client("myreg.io")._resolve_credentials()
        assert creds is not None
        self.assertEqual((creds.username, creds.secret), ("dockeruser", "dockerpass"))

    def test_no_credentials_returns_none(self):
        with patch.dict("os.environ", {"DOCKER_CONFIG": "/nonexistent-dir"}, clear=True):
            with patch("netrc.netrc", side_effect=OSError):
                creds = self._client("someregistry.io")._resolve_credentials()
        self.assertIsNone(creds)


if __name__ == "__main__":
    unittest.main()
