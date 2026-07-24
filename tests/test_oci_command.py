import argparse
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty._internal.cli.commands import oci as oci_command
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


def _ns(oci_command_name: str, *recipes: str, **over: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "oci_command": oci_command_name,
        "recipe": list(recipes),
        "build_type": "Release",
        "target_os": None,
        "target_arch": None,
        "output": None,
        "registry": "ghcr.io",
        "owner": "o3de",
        "prefix": "thirdparty",
        "tag": None,
        "username": None,
        "password": None,
        "dry_run": False,
    }
    values.update(over)
    return argparse.Namespace(**values)


def _make_project(tmp: str, *, staged: bool = True) -> "tuple[Path, str]":
    root = Path(tmp)
    recipes_root = root / "recipes"
    (recipes_root / "zlib").mkdir(parents=True)
    (recipes_root / "zlib" / "recipe.py").write_text(_RECIPE, encoding="utf-8")

    cls = try_load_recipe_class(recipes_root, "zlib")
    assert cls is not None
    package_id = compute_package_id(cls, recipes_root, "zlib", resolve_version(cls))

    if staged:
        pkg = root / "build" / "zlib" / package_id / "package"
        (pkg / "include").mkdir(parents=True)
        (pkg / "include" / "zlib.h").write_text("int x;", encoding="utf-8")
        (pkg / "lib").mkdir()
        (pkg / "lib" / "z.lib").write_bytes(b"BINARYLIB")
    return root, package_id


def _run(root: Path, ns: argparse.Namespace) -> str:
    prev = Path.cwd()
    os.chdir(root)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            oci_command.oci(ns)
    finally:
        os.chdir(prev)
    return buf.getvalue()


class OciBuildTests(unittest.TestCase):
    def test_build_produces_valid_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, package_id = _make_project(tmp)
            _run(root, _ns("build", "zlib"))

            layout = root / "build" / "zlib" / package_id / "dist" / "oci"
            self.assertEqual(
                json.loads((layout / "oci-layout").read_text()),
                {"imageLayoutVersion": "1.0.0"})

            index = json.loads((layout / "index.json").read_text())
            self.assertEqual(len(index["manifests"]), 1)
            desc = index["manifests"][0]
            self.assertIn("architecture", desc["platform"])
            self.assertIn("os", desc["platform"])

            for blob in (layout / "blobs" / "sha256").iterdir():
                self.assertEqual(hashlib.sha256(blob.read_bytes()).hexdigest(), blob.name)

            manifest = json.loads(
                (layout / "blobs" / "sha256" / desc["digest"].split(":")[1]).read_bytes())
            self.assertEqual(len(manifest["layers"]), 1)
            config = json.loads(
                (layout / "blobs" / "sha256" / manifest["config"]["digest"].split(":")[1]).read_bytes())
            self.assertNotEqual(config["rootfs"]["diff_ids"][0], manifest["layers"][0]["digest"])

            ann = manifest["annotations"]
            self.assertEqual(ann["thirdparty.package_id"], package_id)
            self.assertIn("thirdparty.os", ann)
            self.assertIn("thirdparty.arch", ann)
            self.assertEqual(ann["thirdparty.build_type"], "Release")

    def test_build_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = _make_project(tmp)
            _run(root, _ns("build", "zlib", output=str(root / "out1")))
            _run(root, _ns("build", "zlib", output=str(root / "out2")))
            d1 = json.loads((root / "out1" / "index.json").read_text())["manifests"][0]["digest"]
            d2 = json.loads((root / "out2" / "index.json").read_text())["manifests"][0]["digest"]
            self.assertEqual(d1, d2)

    def test_build_unbuilt_recipe_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = _make_project(tmp, staged=False)  # recipe exists, nothing built
            with self.assertRaises(SystemExit) as ctx:
                _run(root, _ns("build", "zlib"))
            self.assertEqual(ctx.exception.code, 1)


class OciPushTests(unittest.TestCase):
    def test_push_without_build_exits_nonzero(self):
        # A fully staged package but NO 'oci build' -> push must fail (never repackages/builds).
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = _make_project(tmp)
            with self.assertRaises(SystemExit) as ctx:
                _run(root, _ns("push", "zlib", owner="o3de"))
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
