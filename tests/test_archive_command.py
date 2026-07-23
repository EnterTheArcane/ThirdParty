import argparse
import io
import json
import lzma
import os
import sys
import tarfile
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty._internal.cli.commands import archive as archive_command
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


def _args(*recipes: str, fmt: str = "tar.gz", output: "str | None" = None) -> argparse.Namespace:
    return argparse.Namespace(
        recipe=list(recipes),
        fmt=fmt,
        build_type="Release",
        target_os=None,
        target_arch=None,
        output=output)


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
            archive_command.archive(ns)
    finally:
        os.chdir(prev)
    return buf.getvalue()


class ArchiveCommandTests(unittest.TestCase):
    def test_targz_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, package_id = _make_project(tmp)
            out = _run(root, _args("zlib", fmt="tar.gz")).strip()
            self.assertTrue(out.endswith(".tar.gz"))
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
            root, _ = _make_project(tmp)
            out = _run(root, _args("zlib", fmt="zip")).strip()
            self.assertTrue(out.endswith(".zip"))
            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
                self.assertIn("metadata.json", names)
                self.assertIn("lib/z.lib", names)
                self.assertEqual(zf.read("lib/z.lib"), b"BINARYLIB")

    def test_tar_xz_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = _make_project(tmp)
            out = _run(root, _args("zlib", fmt="tar.xz")).strip()
            self.assertTrue(out.endswith(".tar.xz"))
            # decompresses as xz and opens as tar
            with tarfile.open(fileobj=io.BytesIO(lzma.decompress(Path(out).read_bytes()))) as t:
                self.assertIn("include/zlib.h", set(t.getnames()))

    def test_forward_slash_arcnames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = _make_project(tmp)
            out = _run(root, _args("zlib", fmt="tar.gz")).strip()
            with tarfile.open(out) as t:
                for name in t.getnames():
                    self.assertNotIn("\\", name)

    def test_missing_staged_dir_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = _make_project(tmp, staged=False)
            with self.assertRaises(SystemExit) as ctx:
                _run(root, _args("zlib"))
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
