from thirdparty._internal.model.recipe import RecipeBase
from thirdparty.errors import RecipeException


def android_abi(recipe: RecipeBase, context: str = "host"):
    """
    Returns Android-NDK ABI

    :param recipe: RecipeBase instance
    :param context: either "host", "build" or "target"
    :return: Android-NDK ABI
    """
    if context not in ("host", "build", "target"):
        raise RecipeException(
            f"context argument must be either 'host', 'build' or 'target', "
            f"was '{context}'")

    try:
        settings = getattr(recipe, f"settings_{context}")
    except AttributeError:
        if context == "host":
            settings = recipe.settings
        else:
            raise RecipeException(f"settings_{context} not declared in recipe")
    if settings is None:
        raise RecipeException(f"settings_{context}=None in recipe")
    arch = settings.arch
    # https://cmake.org/cmake/help/latest/variable/CMAKE_ANDROID_ARCH_ABI.html
    return {
        "ARM": "arm64-v8a", "X64": "x86_64",
    }.get(arch, arch)
