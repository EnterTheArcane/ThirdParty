
from thirdparty._internal.errors import recipe_exception_formatter
from thirdparty.recipe import RecipeBase


def run_configure_method(recipe: RecipeBase):
    initial_requires_count = len(recipe._requires)

    # default implementation removes compiler.cstd
    recipe.settings.compiler_c_standard = None

    with recipe_exception_formatter(recipe, "configure"):
        recipe.configure()

    if initial_requires_count != len(recipe._requires):
        recipe.output.warning("Requirements should only be added in the requirements() method, not configure().", warn_tag="deprecated")

    with recipe_exception_formatter(recipe, "requirements"):
        recipe.requirements()
