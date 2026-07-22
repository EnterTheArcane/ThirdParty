import sys
import unittest
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty.common.generator import generate
from thirdparty._internal.model.recipe import RecipeBase


class Recipe(RecipeBase):
    name = "generator-test"
    version = "1.0"
    license = "MIT"


class CommonGeneratorTests(unittest.TestCase):
    def test_generate_instantiates_generator_with_recipe(self):
        recipe = Recipe()

        class TestGenerator:
            def __init__(self, recipe_arg: RecipeBase):
                self.recipe = recipe_arg

            def generate(self) -> RecipeBase:
                return self.recipe

        self.assertIs(generate(recipe, TestGenerator), recipe)

    def test_generate_forwards_arguments_and_return_value(self):
        calls: list[tuple[RecipeBase, tuple[Any, ...], dict[str, Any]]] = []
        recipe = Recipe()

        class TestGenerator:
            def __init__(self, recipe_arg: RecipeBase):
                self.recipe = recipe_arg

            def generate(self, *args: Any, **kwargs: Any) -> str:
                calls.append((self.recipe, args, kwargs))
                return "generated"

        result = generate(recipe, TestGenerator, "arg", scope="build")

        self.assertEqual(result, "generated")
        self.assertEqual(calls, [(recipe, ("arg",), {"scope": "build"})])


if __name__ == "__main__":
    unittest.main()
