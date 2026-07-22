import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty._internal.cli.commands import outdated as outdated_command


def _args(**overrides: bool) -> argparse.Namespace:
    values = {
        "all": False,
        "missing": False,
        "outdated_only": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class OutdatedCommandTests(unittest.TestCase):
    def test_outdated_only_filters_non_outdated_statuses(self):
        recipes = {
            "ahead": ("2.0.0", "1.0.0"),
            "old": ("1.0.0", "1.2.0"),
            "same": ("1.0.0", "1.0.0"),
            "unknown": ("1.0.0", "None"),
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipes_root = root / "recipes"
            recipes_root.mkdir()
            for name, (version, latest) in recipes.items():
                recipe_dir = recipes_root / name
                recipe_dir.mkdir()
                recipe_dir.joinpath("recipe.py").write_text(
                    "\n".join([
                        "from thirdparty import RecipeBase",
                        "",
                        "class Recipe(RecipeBase):",
                        f"    name = {name!r}",
                        f"    version = {version!r}",
                        "",
                        "    def latest_version(self):",
                        f"        return {latest!r}" if latest != "None" else "        return None",
                        "",
                    ]),
                    encoding="utf-8",
                )

            prev_cwd = Path.cwd()
            os.chdir(root)
            try:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    outdated_command.outdated(_args(outdated_only=True))
            finally:
                os.chdir(prev_cwd)

        output = stdout.getvalue()
        self.assertIn("old", output)
        self.assertIn("OUTDATED", output)
        self.assertNotIn("same", output)
        self.assertNotIn("ahead", output)
        self.assertNotIn("unknown", output)
        self.assertNotIn("up-to-date", output)


if __name__ == "__main__":
    unittest.main()
