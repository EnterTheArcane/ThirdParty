import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty._internal.cli.commands import package as package_command
from thirdparty._internal.loader import compute_package_id, resolve_version, try_load_recipe_class


_RECIPE = "\n".join([
    "from thirdparty import RecipeBase, RecipeOptions",
    "",
    "class _Options(RecipeOptions):",
    "    shared: bool = False",
    "",
    "class Recipe(RecipeBase[_Options]):",
    "    name = 'zlib'",
    "    version = '1.3.2'",
    "    license = 'Zlib'",
    "",
    "    def latest_version(self):",
    "        return None",
    "",
])


def _args(*recipes: str, fmt: str = "oci", output: "str | None" = None) -> argparse.Namespace:
    return argparse.Namespace(
        recipe=list(recipes),
        fmt=fmt,
        build_type="Release",
        target_os=None,
        target_arch=None,
        output=output,
        publish=False,
        owner=None,
        registry="ghcr.io",
        prefix="thirdparty")


def _make_project(tmp: str) -> "tuple[Path, str, Path]":
    """Create recipes/zlib + a staged build tree; return (root, package_id, staged_dir)."""
    root = Path(tmp)
    recipes_root = root / "recipes"
    (recipes_root / "zlib").mkdir(parents=True)
    (recipes_root / "zlib" / "recipe.py").write_text(_RECIPE, encoding="utf-8")

    cls = try_load_recipe_class(recipes_root, "zlib")
    assert cls is not None
    version = resolve_version(cls)
    package_id = compute_package_id(cls, recipes_root, "zlib", version)

    staged = root / "build" / "zlib" / package_id / "package"
    (staged / "include").mkdir(parents=True)
    (staged / "include" / "zlib.h").write_text("int x;", encoding="utf-8")
    (staged / "lib").mkdir()
    (staged / "lib" / "z.lib").write_bytes(b"BINARYLIB")
    return root, package_id, staged


class PackageCommandTests(unittest.TestCase):
    def _run(self, root: Path, args: argparse.Namespace) -> str:
        prev = Path.cwd()
        os.chdir(root)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                package_command.package(args)
        finally:
            os.chdir(prev)
        return buf.getvalue()

    def test_oci_layout_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, package_id, _ = _make_project(tmp)
            self._run(root, _args("zlib"))

            layout = root / "build" / "zlib" / package_id / "dist" / "oci"
            self.assertEqual(
                json.loads((layout / "oci-layout").read_text()),
                {"imageLayoutVersion": "1.0.0"})

            index = json.loads((layout / "index.json").read_text())
            self.assertTrue(index["mediaType"].endswith("index.v1+json"))
            self.assertEqual(len(index["manifests"]), 1)
            desc = index["manifests"][0]
            self.assertIn("architecture", desc["platform"])
            self.assertIn("os", desc["platform"])

            # Every blob's filename equals the sha256 of its bytes.
            for blob in (layout / "blobs" / "sha256").iterdir():
                self.assertEqual(hashlib.sha256(blob.read_bytes()).hexdigest(), blob.name)

            manifest = json.loads(
                (layout / "blobs" / "sha256" / desc["digest"].split(":")[1]).read_bytes())
            self.assertEqual(len(manifest["layers"]), 1)

            config = json.loads(
                (layout / "blobs" / "sha256" / manifest["config"]["digest"].split(":")[1]).read_bytes())
            diff_id = config["rootfs"]["diff_ids"][0]
            self.assertNotEqual(diff_id, manifest["layers"][0]["digest"])

            ann = manifest["annotations"]
            self.assertEqual(ann["io.o3de.thirdparty.package_id"], package_id)
            self.assertIn("io.o3de.thirdparty.os", ann)
            self.assertIn("io.o3de.thirdparty.arch", ann)
            self.assertEqual(ann["io.o3de.thirdparty.build_type"], "Release")

    def test_oci_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, package_id, _ = _make_project(tmp)
            self._run(root, _args("zlib", output=str(root / "out1")))
            self._run(root, _args("zlib", output=str(root / "out2")))
            d1 = json.loads((root / "out1" / "oci" / "index.json").read_text())["manifests"][0]["digest"]
            d2 = json.loads((root / "out2" / "oci" / "index.json").read_text())["manifests"][0]["digest"]
            self.assertEqual(d1, d2)

    def test_targz_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, package_id, _ = _make_project(tmp)
            out = self._run(root, _args("zlib", fmt="tar.gz")).strip()
            with tarfile.open(out) as t:
                names = set(t.getnames())
                self.assertIn("metadata.json", names)
                self.assertIn("include/zlib.h", names)
                member = t.extractfile("include/zlib.h")
                assert member is not None
                self.assertEqual(member.read(), b"int x;")
                meta_member = t.extractfile("metadata.json")
                assert meta_member is not None
                meta = json.loads(meta_member.read())
                self.assertEqual(meta["name"], "zlib")
                self.assertEqual(meta["package_id"], package_id)

    def test_zip_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _, _ = _make_project(tmp)
            out = self._run(root, _args("zlib", fmt="zip")).strip()
            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
                self.assertIn("metadata.json", names)
                self.assertIn("lib/z.lib", names)
                self.assertEqual(zf.read("lib/z.lib"), b"BINARYLIB")

    def test_forward_slash_arcnames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _, _ = _make_project(tmp)
            out = self._run(root, _args("zlib", fmt="tar.gz")).strip()
            with tarfile.open(out) as t:
                for name in t.getnames():
                    self.assertNotIn("\\", name)

    def test_missing_staged_dir_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipes_root = root / "recipes"
            (recipes_root / "zlib").mkdir(parents=True)
            (recipes_root / "zlib" / "recipe.py").write_text(_RECIPE, encoding="utf-8")
            # No build/ tree -> package not built.
            with self.assertRaises(SystemExit) as ctx:
                self._run(root, _args("zlib"))
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
