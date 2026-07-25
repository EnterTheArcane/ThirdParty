from thirdparty._internal.model.recipe import RecipeBase
from thirdparty._internal.model.toolchain import find_toolchain
from thirdparty.errors import RecipeException, RecipeInvalidConfiguration
from thirdparty._internal.model.version import Version


def msvc_platform_from_arch(arch: str) -> str:
    return {"X64": "x64", "ARM": "ARM64"}[arch]


def check_min_vs(recipe: RecipeBase, version: str, raise_invalid: bool = True) -> bool:
    """
    This is a helper method to allow the migration of 1.X -> 2.0 and VisualStudio -> msvc settings
    without breaking recipes.
    The legacy "Visual Studio" with different toolset is not managed, not worth the complexity.

    Recipe-provided toolchains (settings.compiler_recipe == "msvc") are version-less in
    settings - the msvc package pins a modern toolset - so the check passes.

    :param raise_invalid: ``bool`` Whether to raise or return False if the version check fails
    :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
    :param version: ``str`` Visual Studio or msvc version number.
    """
    compiler = recipe.settings.compiler
    compiler_version = None
    if compiler == "Visual Studio":
        compiler_version = recipe.settings.compiler_version
        compiler_version = {
            "17": "193", "16": "192", "15": "191", "14": "190", "12": "180", "11": "170",
        }.get(compiler_version)  # pyright: ignore[reportArgumentType]  # dict.get tolerates a None key (returns None)
    elif compiler == "msvc":
        compiler_version = recipe.settings.compiler_version
        msvc_update = recipe.conf.tools.microsoft.msvc_update
        compiler_update = msvc_update or recipe.settings.compiler_update
        if compiler_version and compiler_update is not None:
            compiler_version += f".{compiler_update}"

    if compiler_version and Version(compiler_version) < version:
        if raise_invalid:
            msg = f"This package doesn't work with VS compiler version '{compiler_version}'" \
                  f", it requires at least '{version}'"
            raise RecipeInvalidConfiguration(msg)
        else:
            return False
    return True


def msvc_version_to_vs_ide_version(version: str | None) -> str:
    """
    Gets the Visual Studio IDE version given the ``msvc`` compiler one.

    :param version: ``str`` or ``int`` msvc version
    :return: VS IDE version
    """
    _visuals = {
        "170": "11", "180": "12", "190": "14", "191": "15", "192": "16", "193": "17", "194": "17",  # Note both 193 and 194 belong to VS 17 2022
        "195": "18",
    }
    return _visuals[str(version)]


def msvc_version_to_toolset_version(version: str | None) -> str | None:
    """
    Gets the Visual Studio IDE toolset version given the ``msvc`` compiler one.

    :param version: ``str`` or ``int`` msvc version
    :return: VS IDE toolset version
    """
    toolsets = {
        "170": "v110", "180": "v120", "190": "v140", "191": "v141", "192": "v142", "193": "v143", "194": "v143", "195": "v145",
    }
    return toolsets.get(str(version))


def vs_ide_version(recipe: RecipeBase) -> str:
    """
    Gets the VS IDE version as string. It'll use the ``compiler.version`` (if exists) and/or the
    ``tools.msbuild:vs_version`` if ``compiler`` is ``msvc``.

    :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
    :return: ``str`` Visual IDE version number.
    """
    compiler = recipe.settings.compiler
    compiler_version = recipe.settings.compiler_version
    if compiler == "msvc":
        toolset_override = recipe.conf.tools.msbuild.vs_version
        if toolset_override:
            visual_version = toolset_override
        else:
            visual_version = msvc_version_to_vs_ide_version(compiler_version)
    else:
        visual_version = compiler_version
    return visual_version  # pyright: ignore[reportReturnType]  # defensive: compiler_version is non-None for the msvc path callers rely on


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
    compiler_version = settings.compiler_version
    if compiler == "msvc":
        subs_toolset = settings.compiler_toolset
        if subs_toolset:
            return subs_toolset
        return msvc_version_to_toolset_version(compiler_version)
    if compiler == "clang":
        return "ClangCL"
