from thirdparty._internal.model.recipe import RecipeBase
from thirdparty._internal.model.toolchain import find_toolchain
from thirdparty.errors import RecipeException


# The msvc package pins the toolset (VS 2022 / v143) and the clang package pins ClangCL,
# so the fallback toolset is a constant rather than something mapped from a compiler
# version setting.
VS_PLATFORM_TOOLSET = "v143"


def msvc_platform_from_arch(arch: str) -> str:
    return {"X64": "x64", "ARM": "ARM64"}[arch]


def msvc_runtime_flag(recipe: RecipeBase) -> str:
    """
    Gets the MSVC runtime flag given the ``compiler.runtime`` value from the settings.

    :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
    :return: ``str`` runtime flag.
    """
    settings = recipe.settings
    runtime = settings.compiler_runtime
    if runtime is not None:
        if runtime == "static":
            runtime = "MT"
        elif runtime == "dynamic":
            runtime = "MD"
        else:
            raise RecipeException("compiler.runtime should be 'static' or 'dynamic'")
        runtime_type = settings.compiler_runtime_type
        if runtime_type == "Debug":
            runtime = f"{runtime}d"
        return runtime
    return ""


def is_msvc(recipe: RecipeBase, build_context: bool = False) -> bool:
    """
    Validates if the current compiler is ``msvc``.

    :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
    :param build_context: If True, will use the settings from the build context, not host ones
    :return: ``bool`` True, if the host compiler is ``msvc``, otherwise, False.
    """
    if not build_context:
        settings = recipe.settings
    else:
        settings = recipe.settings_build
    return settings.compiler == "msvc"


def is_msvc_static_runtime(recipe: RecipeBase) -> bool:
    """
    Validates when building with Visual Studio or msvc and MT on runtime.

    :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
    :return: ``bool`` True, if ``msvc + runtime MT``. Otherwise, False.
    """
    return is_msvc(recipe) and "MT" in msvc_runtime_flag(recipe)


def msvs_toolset(recipe: RecipeBase) -> str | None:
    """
    Returns the corresponding platform toolset based on the toolchain provider contract
    (settings.compiler_recipe - e.g. "v143" from the msvc package, "ClangCL" from the
    clang package) or, failing that, the compiler settings.

    :param recipe: Recipefile instance to access settings.compiler
    :return: A toolset when the provider/settings determine one. Otherwise, None.
    """
    tc = find_toolchain(recipe)
    if tc is not None and tc.msbuild_toolset:
        return tc.msbuild_toolset

    settings = recipe.settings
    compiler = settings.compiler
    if compiler == "msvc":
        return settings.compiler_toolset or VS_PLATFORM_TOOLSET
    if compiler == "clang":
        return "ClangCL"
