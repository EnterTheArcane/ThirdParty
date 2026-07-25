
from thirdparty._internal.errors import recipe_exception_formatter
from thirdparty._internal.toolchains import injectable
from thirdparty.recipe import RecipeBase


def _inject_toolchain_requires(recipe: RecipeBase):
    """Inject the selected toolchain provider recipe into every consumer.

    One host-context require per consumer; the provider pulls its own ingredients
    (llvm, msvc, windows-sdk, apple-sdk, linux-sysroot, android-ndk) through its own
    requirements, branching on ITS settings (= this recipe's target). Recipes that are
    themselves part of the selected toolchain's layer are skipped to avoid cycles.
    """
    if not injectable(recipe):
        return
    provider = str(recipe.settings.compiler_recipe)
    if provider not in {str(r.name) for r in recipe._requires}:
        recipe.requires(provider)


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

    _inject_toolchain_requires(recipe)
