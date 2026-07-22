import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty._internal.cli.commands import build as build_command
from thirdparty._internal.graph import Graph, Node
from thirdparty import RecipeBase


class _StubRecipe(RecipeBase):
    name = "stub"
    version = "1"
    license = "MIT"

    def latest_version(self):
        return None


def _args(*recipes: str) -> argparse.Namespace:
    return argparse.Namespace(
        recipe=list(recipes),
        build_type="Release",
        generate_only=False,
        resume=None,
        target_os=None,
        target_arch=None,
        dry_run=False,
        force=False,
        exact=False,
        fail_fast=False,
        jobs=None,
    )


class BuildCommandTests(unittest.TestCase):
    def test_build_all_ignores_directories_without_recipe_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipes_root = root / "recipes"
            (recipes_root / "kept").mkdir(parents=True)
            (recipes_root / "kept" / "recipe.py").write_text("class Recipe:\n    pass\n", encoding="utf-8")
            (recipes_root / "leftover-empty-dir").mkdir()

            prev_cwd = Path.cwd()
            os.chdir(root)
            try:
                with patch.object(build_command, "_build_ordered") as build_ordered:
                    build_command.build(_args())
            finally:
                os.chdir(prev_cwd)

        build_ordered.assert_called_once()
        self.assertEqual(build_ordered.call_args.args[2], ["kept"])

    def test_build_rejects_explicit_directory_without_recipe_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipes_root = root / "recipes"
            recipes_root.mkdir(parents=True)
            (recipes_root / "leftover-empty-dir").mkdir()

            prev_cwd = Path.cwd()
            os.chdir(root)
            try:
                stderr = io.StringIO()
                with redirect_stderr(stderr), self.assertRaises(SystemExit) as exc:
                    build_command.build(_args("leftover-empty-dir"))
            finally:
                os.chdir(prev_cwd)

        self.assertEqual(exc.exception.code, 1)
        self.assertIn("recipe not found: leftover-empty-dir", stderr.getvalue())

    def test_ordered_build_skips_dependant_when_dependency_fails(self):
        graph = Graph({
            "ffmpeg": Node("ffmpeg", "1"),
            "openimageio": Node("openimageio", "1", host_deps=["ffmpeg"]),
        })

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipes_root = root / "recipes"
            build_root = root / "build"
            recipes_root.mkdir(parents=True)

            def fail_ffmpeg(*args, **kwargs):
                if args[2] == "ffmpeg":
                    raise RuntimeError("boom")
                raise AssertionError(f"unexpected build: {args[2]}")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                redirect_stdout(stdout),
                redirect_stderr(stderr),
                patch.object(build_command._Graph, "build", return_value=graph),
                patch.object(build_command, "_try_load_recipe_class", return_value=_StubRecipe),
                patch.object(build_command, "_resolve_version", return_value="1"),
                patch.object(build_command, "_is_built", return_value=False),
                patch.object(build_command, "_build_recipe", side_effect=fail_ffmpeg) as build_recipe,
                self.assertRaises(SystemExit) as exc,
            ):
                build_command._build_ordered(
                    recipes_root,
                    build_root,
                    ["openimageio", "ffmpeg"],
                    "Release",
                    jobs=None,
                    resume=None,
                    dry_run=False,
                    force=False,
                    generate_only=False,
                    target_os=None,
                    target_arch=None,
                )

        self.assertEqual(exc.exception.code, 1)
        self.assertEqual([call.args[2] for call in build_recipe.call_args_list], ["ffmpeg"])
        self.assertIn("SKIP openimageio/1 - dependency failed/skipped: ffmpeg", stderr.getvalue())
        self.assertIn("SKIP openimageio (dependency failed/skipped: ffmpeg)", stderr.getvalue())

    def test_failed_build_leaves_build_folder_for_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipes_root = root / "recipes"
            build_root = root / "build"
            recipe_dir = recipes_root / "fails"
            recipe_dir.mkdir(parents=True)
            (recipe_dir / "recipe.py").write_text(
                "\n".join([
                    "from pathlib import Path",
                    "from thirdparty import RecipeBase",
                    "",
                    "class Recipe(RecipeBase):",
                    "    name = 'fails'",
                    "    version = '1'",
                    "    license = 'MIT'",
                    "",
                    "    def build(self):",
                    "        Path('build.log').write_text('failed build log', encoding='utf-8')",
                    "        raise RuntimeError('boom')",
                    "",
                ]),
                encoding="utf-8")

            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()), self.assertRaises(RuntimeError):
                build_command._build_recipe(
                    recipes_root,
                    build_root,
                    "fails",
                    "Release",
                    set(),
                    target_os=None,
                    target_arch=None,
                )

            platform_tag = build_command.detect_platform_tag(None, None)
            build_dir = build_root / "fails" / platform_tag / "build"
            self.assertTrue((build_dir / "build.log").is_file())
            self.assertFalse((build_dir / build_command._COMPLETE_MARKER).exists())

    def test_incomplete_build_folder_is_wiped_before_next_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipes_root = root / "recipes"
            build_root = root / "build"
            recipe_dir = recipes_root / "stale"
            recipe_dir.mkdir(parents=True)
            (recipe_dir / "recipe.py").write_text(
                "\n".join([
                    "from pathlib import Path",
                    "from thirdparty import RecipeBase",
                    "",
                    "class Recipe(RecipeBase):",
                    "    name = 'stale'",
                    "    version = '1'",
                    "    license = 'MIT'",
                    "",
                    "    def build(self):",
                    "        assert not Path('stale.txt').exists()",
                    "        Path('fresh.txt').write_text('fresh build', encoding='utf-8')",
                    "",
                ]),
                encoding="utf-8")

            platform_tag = build_command.detect_platform_tag(None, None)
            build_dir = build_root / "stale" / platform_tag / "build"
            package_dir = build_root / "stale" / platform_tag / "package"
            build_dir.mkdir(parents=True)
            package_dir.mkdir(parents=True)
            (build_dir / "stale.txt").write_text("old partial build", encoding="utf-8")
            (package_dir / "stale.txt").write_text("old partial package", encoding="utf-8")

            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                build_command._build_recipe(
                    recipes_root,
                    build_root,
                    "stale",
                    "Release",
                    set(),
                    target_os=None,
                    target_arch=None,
                )

            self.assertFalse((build_dir / "stale.txt").exists())
            self.assertFalse(package_dir.exists())
            self.assertTrue((build_dir / "fresh.txt").is_file())
            self.assertTrue((build_dir / build_command._COMPLETE_MARKER).is_file())


if __name__ == "__main__":
    unittest.main()
