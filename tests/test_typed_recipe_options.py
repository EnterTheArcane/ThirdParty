import sys
import unittest
from pathlib import Path
from typing import Any, Literal


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty._internal.model.options import RecipeOptions as RecipeOptionsBase, _derive_options
from thirdparty._internal.model.recipe import RecipeBase
from thirdparty.errors import RecipeException


class TypedRecipeOptionsTests(unittest.TestCase):
    def test_typed_options_derive_recipe_metadata(self):
        class RecipeOptions(RecipeOptionsBase):
            shared: bool = False
            mode: Literal[False, "libjpeg", "turbo"] = "libjpeg"
            package_name: str | None = None
            ca_path: Literal[False, "auto"] | str = "auto"
            jobs: int = 4
            extra: Any = None

        class Recipe(RecipeBase[RecipeOptions]):
            name = "typed"
            version = "1.0"
            license = "MIT"

        options, defaults = _derive_options(RecipeOptions)

        self.assertEqual(options, {
            "shared": [True, False],
            "mode": [False, "libjpeg", "turbo"],
            "package_name": [None, "ANY"],
            "ca_path": [False, "auto", "ANY"],
            "jobs": ["ANY"],
            "extra": ["ANY"],
        })
        self.assertEqual(defaults, {
            "shared": False,
            "mode": "libjpeg",
            "package_name": None,
            "ca_path": "auto",
            "jobs": 4,
            "extra": None,
        })

    def test_typed_options_initialize_runtime_options(self):
        class RecipeOptions(RecipeOptionsBase):
            shared: bool = True

        class Recipe(RecipeBase[RecipeOptions]):
            name = "typed-runtime"
            version = "1.0"
            license = "MIT"

        recipe = Recipe()

        self.assertTrue(recipe.options.shared)
        self.assertEqual(recipe.options.dumps(), "shared=True")

    def test_old_dictionary_options_are_rejected(self):
        with self.assertRaisesRegex(RecipeException, "explicit options/default_options"):
            class Recipe(RecipeBase):
                name = "old-style"
                version = "1.0"
                license = "MIT"
                options = {"shared": [True, False]}
                default_options = {"shared": False}

    def test_typed_options_allow_missing_defaults(self):
        class RecipeOptions(RecipeOptionsBase):
            shared: bool

        class Recipe(RecipeBase[RecipeOptions]):
            name = "missing-default"
            version = "1.0"
            license = "MIT"

        options, defaults = _derive_options(RecipeOptions)
        self.assertEqual(options, {"shared": [True, False]})
        self.assertEqual(defaults, {})

    def test_typed_options_support_possible_value_overrides(self):
        class RecipeOptions(RecipeOptionsBase):
            thread_model: str

        RecipeOptions.__possible_values__ = {
            "thread_model": ["posix", "windows", "disabled"],
        }

        class Recipe(RecipeBase[RecipeOptions]):
            name = "possible-values"
            version = "1.0"
            license = "MIT"

        options, defaults = _derive_options(RecipeOptions)
        self.assertEqual(options, {"thread_model": ["posix", "windows", "disabled"]})
        self.assertEqual(defaults, {})

    def test_typed_options_support_non_identifier_names(self):
        class RecipeOptions(RecipeOptionsBase):
            __annotations__ = {"386": bool}
            __defaults__ = {"386": False}

        class Recipe(RecipeBase[RecipeOptions]):
            name = "invalid-identifier"
            version = "1.0"
            license = "MIT"

        options, defaults = _derive_options(RecipeOptions)
        self.assertEqual(options, {"386": [True, False]})
        self.assertEqual(defaults, {"386": False})

    def test_typed_options_reject_unsupported_annotations(self):
        class RecipeOptions(RecipeOptionsBase):
            values: list[str] = []

        with self.assertRaisesRegex(RecipeException, "Unsupported typed option"):
            class Recipe(RecipeBase[RecipeOptions]):
                name = "unsupported"
                version = "1.0"
                license = "MIT"

    def test_typed_options_reject_explicit_option_dictionaries(self):
        class RecipeOptions(RecipeOptionsBase):
            shared: bool = False

        with self.assertRaisesRegex(RecipeException, "explicit options/default_options"):
            class Recipe(RecipeBase[RecipeOptions]):
                name = "conflict"
                version = "1.0"
                license = "MIT"
                options = {"shared": [True, False]}


if __name__ == "__main__":
    unittest.main()
