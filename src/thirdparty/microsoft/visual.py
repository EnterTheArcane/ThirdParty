from thirdparty._internal.model.recipe import RecipeBase
from thirdparty._internal.model.settings import MSVC_COMPILERS
from thirdparty._internal.model.toolchain import find_toolchain
from thirdparty.errors import RecipeException


# The msvc package pins the toolset (VS 2022 / v143) and the clang-cl package pins
# ClangCL, so the fallback toolset is a constant rather than something mapped from a
# compiler version setting.
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
    Validates if the current compiler is MSVC-*like*, i.e. ``cl.exe`` or ``clang-cl``.

    This mirrors CMake's ``MSVC`` variable. clang-cl targets the MSVC ABI, accepts cl.exe's
    flag syntax and links against the MSVC CRT, so everything that branches on "this is an
    MSVC-style build" - ``lib``-prefixed/``.lib`` outputs, ``/``-flags, ``-LIBPATH:`` link
    lines, the Windows CRT shims - applies to both. Where the two genuinely differ, use
    :func:`is_cl_exe` or :func:`is_clang_cl`.

    :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
    :param build_context: If True, will use the settings from the build context, not host ones
    :return: ``bool`` True, if the compiler is cl.exe or clang-cl, otherwise, False.
    """
    settings = recipe.settings_build if build_context else recipe.settings
    return settings.compiler in MSVC_COMPILERS


def is_cl_exe(recipe: RecipeBase, build_context: bool = False) -> bool:
    """
    Validates if the current compiler is Microsoft's ``cl.exe`` specifically.

    Only for the cases clang-cl does not share: cl.exe-only flags, ``CC=cl`` style build
    variables, and link.exe-only behaviour. Prefer :func:`is_msvc` otherwise.

    :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
    :param build_context: If True, will use the settings from the build context, not host ones
    :return: ``bool`` True, if the compiler is ``msvc``, otherwise, False.
    """
    settings = recipe.settings_build if build_context else recipe.settings
    return settings.compiler == "msvc"


def is_clang_cl(recipe: RecipeBase, build_context: bool = False) -> bool:
    """
    Validates if the current compiler is ``clang-cl``, clang's MSVC-compatible front.

    Only for the cases cl.exe does not share: the LLVM binutils (``llvm-lib``/``lld-link``)
    and clang diagnostics. Prefer :func:`is_msvc` otherwise.

    :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
    :param build_context: If True, will use the settings from the build context, not host ones
    :return: ``bool`` True, if the compiler is ``clang-cl``, otherwise, False.
    """
    settings = recipe.settings_build if build_context else recipe.settings
    return settings.compiler == "clang-cl"


def is_msvc_static_runtime(recipe: RecipeBase) -> bool:
    """
    Validates when building with an MSVC-like compiler and MT on runtime.

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
    if compiler == "clang-cl":
        return "ClangCL"
