import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty._internal.errors import AuthenticationException
from thirdparty._internal.pack.ghcr import GHCRClient
from thirdparty._internal.pack.layout import MT_INDEX
from thirdparty._internal.pack.meta import PackageMeta
from thirdparty._internal.pack.oci import OciBackend


class _FakeResponse:
    def __init__(self, status_code: int, *, json_body: "dict[str, Any] | None" = None,
                 headers: "dict[str, str] | None" = None) -> None:
        self.status_code = status_code
        self._json = json_body or {}
        self.headers = headers or {}
        self.text = json.dumps(self._json)

    def json(self) -> "dict[str, Any]":
        return self._json


class _FakeHttp:
    """Records calls and returns canned OCI-registry responses; stores the pushed index."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.stored_index: "dict[str, Any] | None" = None

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append(("GET", url))
        if url.endswith("/token"):
            return _FakeResponse(200, json_body={"token": "fake-bearer"})
        if "/manifests/" in url:
            if self.stored_index is not None:
                return _FakeResponse(200, json_body=self.stored_index)
            return _FakeResponse(404)
        return _FakeResponse(404)

    def head(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append(("HEAD", url))
        return _FakeResponse(404)  # blob not present -> force upload

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append(("POST", url))
        return _FakeResponse(202, headers={"Location": url + "abc-upload-id"})

    def put(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append(("PUT", url))
        headers = kwargs.get("headers", {})
        if headers.get("Content-Type") == MT_INDEX:
            self.stored_index = json.loads(kwargs["data"])
        return _FakeResponse(201)


def _meta(os_name: str, arch: str, package_id: str) -> PackageMeta:
    return PackageMeta(
        name="zlib", version="1.3.2", package_id=package_id,
        os=os_name, arch=arch, build_type="Release")


def _build_layout(tmp: Path, meta: PackageMeta, sub: str) -> Path:
    staged = tmp / sub / "package"
    (staged / "lib").mkdir(parents=True)
    (staged / "lib" / "z.lib").write_bytes(b"BINARY-" + meta.arch.encode())
    out = tmp / sub / "oci"
    OciBackend().pack(staged, out, meta)
    return out


class PublishTests(unittest.TestCase):
    def test_push_call_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _build_layout(Path(tmp), _meta("Windows", "X64", "windows-x64"), "win")
            http = _FakeHttp()
            with patch.dict("os.environ", {"GH_TOKEN": "t"}, clear=False):
                client = GHCRClient("o3de", "zlib", http=http)
                client.push_layout(layout, "1.3.2")

            methods = [m for m, _ in http.calls]
            # token first
            self.assertEqual(methods[0], "GET")
            self.assertTrue(http.calls[0][1].endswith("/token"))
            # blob flow present: HEAD -> POST -> PUT for each of 2 blobs (config + layer)
            self.assertEqual(methods.count("HEAD"), 2)
            self.assertEqual(methods.count("POST"), 2)
            # manifest PUT + index GET + index PUT happen after blobs
            self.assertIn("PUT", methods)
            # index was written with exactly this platform
            assert http.stored_index is not None
            self.assertEqual(len(http.stored_index["manifests"]), 1)
            self.assertEqual(
                http.stored_index["manifests"][0]["platform"],
                {"architecture": "amd64", "os": "windows"})

    def test_second_platform_merges_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            win = _build_layout(Path(tmp), _meta("Windows", "X64", "windows-x64"), "win")
            lin = _build_layout(Path(tmp), _meta("Linux", "ARM", "linux-arm"), "lin")
            http = _FakeHttp()
            with patch.dict("os.environ", {"GH_TOKEN": "t"}, clear=False):
                client = GHCRClient("o3de", "zlib", http=http)
                client.push_layout(win, "1.3.2")
                client.push_layout(lin, "1.3.2")

            assert http.stored_index is not None
            platforms = sorted(
                (m["platform"]["os"], m["platform"]["architecture"])
                for m in http.stored_index["manifests"])
            self.assertEqual(platforms, [("linux", "arm64"), ("windows", "amd64")])

    def test_dry_run_makes_no_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _build_layout(Path(tmp), _meta("Windows", "X64", "windows-x64"), "win")
            http = _FakeHttp()
            client = GHCRClient("o3de", "zlib", http=http)
            digest = client.push_layout(layout, "1.3.2", dry_run=True)
            self.assertEqual(http.calls, [])
            self.assertTrue(digest.startswith("sha256:"))

    def test_missing_token_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _build_layout(Path(tmp), _meta("Windows", "X64", "windows-x64"), "win")
            http = _FakeHttp()
            with patch.dict("os.environ", {}, clear=True):
                client = GHCRClient("o3de", "zlib", http=http)
                with self.assertRaises(AuthenticationException):
                    client.push_layout(layout, "1.3.2")


if __name__ == "__main__":
    unittest.main()
