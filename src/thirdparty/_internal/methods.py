
from thirdparty._internal.errors import recipe_exception_formatter
from thirdparty.recipe import RecipeBase


_WINDOWS_CROSS_TOOLCHAIN = ("llvm", "msvc", "windows-sdk")


def _inject_windows_cross_requires(recipe: RecipeBase):
    """Recipes cross-targeting Windows need the SDK + MSVC CRT (host context, target arch)
    and the llvm toolchain (build context); injected here so recipes stay agnostic."""
    if recipe.settings.os != "Windows" or recipe.settings_build.os == "Windows":
        return
    if getattr(recipe, "name", None) in _WINDOWS_CROSS_TOOLCHAIN:
        return
    existing = {str(r.name) for r in recipe._requires}
    if "windows-sdk" not in existing:
        recipe.requires("windows-sdk")
    if "msvc" not in existing:
        recipe.requires("msvc")
    if "llvm" not in existing:
        recipe.requires_tool("llvm")


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

    _inject_windows_cross_requires(recipe)
