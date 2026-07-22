import os
import textwrap

from thirdparty._internal.model.recipe import RecipeBase
from thirdparty._internal.util.detect_vs import vs_installation_path
from thirdparty._internal.util.files import save
from thirdparty.errors import RecipeException, RecipeInvalidConfiguration
from thirdparty._internal.model.version import Version

RECIPE_VCVARS = "vcvars_env"


def msvc_platform_from_arch(arch: str) -> str:
    return {"X64": "x64", "ARM": "ARM64"}[arch]


def check_min_vs(recipe: RecipeBase, version: str, raise_invalid: bool = True) -> bool:
    """
    This is a helper method to allow the migration of 1.X -> 2.0 and VisualStudio -> msvc settings
    without breaking recipes.
    The legacy "Visual Studio" with different toolset is not managed, not worth the complexity.

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


class VCVars:
    """
    VCVars class generator to generate a ``vcvars_env.bat`` script that activates the correct
    Visual Studio prompt.

    This generator will be automatically called by other generators such as ``CMakeToolchain``
    when considered necessary, for example if building with Visual Studio compiler using the
    CMake ``Ninja`` generator, which needs an active Visual Studio prompt.
    Then, it is not necessary to explicitly instantiate this generator in most cases.
    """

    def __init__(self, recipe: RecipeBase):
        """
        :param recipe: ``RecipeBase object`` The current recipe object. Always use ``self``.
        """
        self._recipe = recipe

    def generate(self, scope: str = "build"):
        """
        Creates a ``vcvars_env.bat`` file that calls Visual ``vcvars`` with the necessary
        args to activate the correct Visual Studio prompt matching the Recipe settings.

        :param scope: ``str`` activation scope, by default "build". It means it will add a
                      call to this ``vcvars_env.bat`` from the aggregating general
                      ``buildenv.bat``, which is the script that will be called by default
                      in ``run(self, ...)`` calls and build helpers such as ``cmake.configure()``
                      and ``cmake.build()``.
        """
        recipe = self._recipe

        os_ = recipe.settings.os
        build_os_ = recipe.settings_build.os

        if (os_ != "Windows" and os_ != "WindowsStore") or build_os_ != "Windows":
            return

        compiler = recipe.settings.compiler
        if compiler not in ("msvc", "clang"):
            return

        vs_install_path = recipe.conf.tools.msbuild.installation_path
        if vs_install_path == "":  # Empty string means "disable"
            return

        vs_version, vcvars_ver = _vcvars_versions(recipe)
        if vs_version is None:
            return

        vcvarsarch = _vcvars_arch(recipe)

        winsdk_version = recipe.conf.tools.microsoft.winsdk_version
        winsdk_version = winsdk_version or recipe.settings.os_version
        # The vs_install_path is like
        # C:\Program Files (x86)\Microsoft Visual Studio\2019\Community
        # C:\Program Files (x86)\Microsoft Visual Studio\2017\Community
        # C:\Program Files (x86)\Microsoft Visual Studio 14.0
        vcvars = vcvars_command(
            vs_version, architecture=vcvarsarch, platform_type=None, winsdk_version=winsdk_version, vcvars_ver=vcvars_ver, vs_install_path=vs_install_path)

        # Quiet by default: drop the "Activating environment" echo and swallow vcvarsall's
        # "[vcvarsall.bat] Environment initialized for: ..." stdout (env vars still get set).
        # `build --verbose` restores both. stderr is kept so real vcvars errors still surface.
        verbose = recipe.conf.tools.compilation.verbose
        activation_echo = (
            f"echo vcvars_env.bat: Activating environment Visual Studio {vs_version} - {vcvarsarch} - winsdk_version={winsdk_version} - vcvars_ver={vcvars_ver}"
            if verbose else "rem vcvars_env.bat: activating environment (quiet)")
        vcvars_call = vcvars if verbose else f"{vcvars} >nul"
        content = textwrap.dedent(
            f"""
            @echo off
            set __VSCMD_ARG_NO_LOGO=1
            set VSCMD_SKIP_SENDTELEMETRY=1
            {activation_echo}
            {vcvars_call}
            """)
        from thirdparty.env.environment import create_env_script
        recipe_vcvars_bat = f"{RECIPE_VCVARS}.bat"
        create_env_script(recipe, content, recipe_vcvars_bat, scope)
        _create_deactivate_vcvars_file(recipe, recipe_vcvars_bat)

        is_ps1 = self._recipe.conf.tools.env.virtualenv.powershell
        if is_ps1:
            content_ps1 = textwrap.dedent(
                rf"""
                if (-not $env:VSCMD_ARG_VCVARS_VER){{
                    Push-Location "$PSScriptRoot"
                    cmd /c "vcvars_env.bat&set" |
                    foreach {{
                    if ($_ -match "=") {{
                        $v = $_.split("=", 2); set-item -force -path "ENV:\$($v[0])"  -value "$($v[1])"
                    }}
                    }}
                    Pop-Location
                    write-host vcvars_env.ps1: Activated environment}}
                """).strip()
            recipe_vcvars_ps1 = f"{RECIPE_VCVARS}.ps1"
            create_env_script(recipe, content_ps1, recipe_vcvars_ps1, scope)
            _create_deactivate_vcvars_file(recipe, recipe_vcvars_ps1)


def _create_deactivate_vcvars_file(recipe: RecipeBase, filename: str):
    if recipe.conf.tools.env.deactivation_mode == "function":
        return
    deactivate_filename = f"deactivate_{filename}"
    message = f"[{deactivate_filename}]: *** vcvars env cannot be deactivated ***\n"
    is_ps1 = filename.endswith(".ps1")
    if is_ps1:
        content = f"Write-Host {message}"
    else:
        content = f"echo {message}"
    path = os.path.join(recipe.folders.generators, deactivate_filename)
    save(path, content)


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


def vcvars_command(
    version: str, architecture: str | None = None, platform_type: str | None = None, winsdk_version: str | None = None, vcvars_ver: str | None = None, start_dir_cd: bool = True, vs_install_path: str | os.PathLike[str] | None = None):
    """
    Recipe-agnostic construction of vcvars command
    https://docs.microsoft.com/en-us/cpp/build/building-on-the-command-line

    :param version: ``str`` Visual Studio version.
    :param architecture: ``str`` Specifies the host and target architecture to use.
    :param platform_type: ``str`` Allows you to specify ``store`` or ``uwp`` as the platform type.
    :param winsdk_version: ``str`` Specifies the version of the Windows SDK to use.
    :param vcvars_ver: ``str`` Specifies the Visual Studio compiler toolset to use.
    :param start_dir_cd: ``bool`` If ``True``, the command will execute
                         ``set "VSCMD_START_DIR=%CD%`` at first.
    :param vs_install_path: ``str`` Visual Studio installation path.
    :return: ``str`` complete _vcvarsall_ command.
    """
    cmd: list[str] = []
    if start_dir_cd:
        cmd.append('set "VSCMD_START_DIR=%CD%" &&')

    # The "call" is useful in case it is called from another .bat script
    cmd.append('call "%s" ' % _vcvars_path(version, vs_install_path))
    if architecture:
        cmd.append(architecture)
    if platform_type:
        cmd.append(platform_type)
    if winsdk_version:
        cmd.append(winsdk_version)
    if vcvars_ver:
        cmd.append("-vcvars_ver=%s" % vcvars_ver)
    return " ".join(cmd)


def _vcvars_path(version: str, vs_install_path: str | os.PathLike[str] | None) -> str:
    # TODO: This comes from upstream_source/client/tools/win.py vcvars_command()
    vs_path = vs_install_path or vs_installation_path(version)
    if not vs_path or not os.path.isdir(vs_path):
        raise RecipeException(
            f"VS non-existing installation: Visual Studio {version}. "
            "If using a non-default toolset from a VS IDE version consider "
            "specifying it with the 'tools.msbuild:vs_version' conf")

    if int(version) > 14:
        vcpath = os.path.join(vs_path, "VC/Auxiliary/Build/vcvarsall.bat")
    else:
        vcpath = os.path.join(vs_path, "VC/vcvarsall.bat")
    vcpath = os.path.normpath(vcpath)
    return vcpath


def _vcvars_versions(recipe: RecipeBase) -> tuple[str | None, str | None]:
    compiler = recipe.settings.compiler
    msvc_update = recipe.conf.tools.microsoft.msvc_update
    if compiler == "clang":
        # The vcvars only needed for LLVM/Clang and VS ClangCL, who define runtime
        if not recipe.settings.compiler_runtime:
            # NMake Makefiles will need vcvars activated, for VS target, defined with runtime
            return None, None
        toolset_version = recipe.settings.compiler_runtime_version
        vs_version = {
            "v140": "14", "v141": "15", "v142": "16", "v143": "17", "v144": "17", "v145": "18",
        }.get(toolset_version)  # pyright: ignore[reportArgumentType]  # dict.get tolerates a None key (returns None)
        if vs_version is None:
            raise RecipeException(
                "Visual Studio Runtime version (v140-v145) not defined. Please, "
                "add the compiler.runtime_version=[v140-v145] setting to your "
                "profile.")
        vcvars_ver = {
            "v140": "14.0", "v141": "14.1", "v142": "14.2", "v143": "14.3", "v144": "14.4", "v145": "14.5",
        }.get(toolset_version)  # pyright: ignore[reportArgumentType]  # dict.get tolerates a None key (returns None)
        if vcvars_ver and msvc_update is not None:
            vcvars_ver += f"{msvc_update}"
    else:
        vs_version = vs_ide_version(recipe)
        if int(vs_version) <= 14:
            vcvars_ver = None
        else:
            compiler_version = str(recipe.settings.compiler_version)
            compiler_update = msvc_update or (recipe.settings.compiler_update or "")
            # The equivalent of compiler 19.26 is toolset 14.26
            vcvars_ver = f"14.{compiler_version[-1]}{compiler_update}"
    return vs_version, vcvars_ver


def _vcvars_arch(recipe: RecipeBase) -> str:
    """
    Computes the vcvars command line architecture based on recipe settings (host) and
    settings_build.
    """
    settings_host = recipe.settings
    settings_build = recipe.settings_build

    arch_host = str(settings_host.arch)
    arch_build = str(settings_build.arch)

    arch = None
    if arch_build == "X64":
        arch = {
            "X64": "amd64", "ARM": "amd64_arm64",
        }.get(arch_host)
    elif arch_build == "ARM":
        arch = {
            "X64": "arm64_x64", "ARM": "arm64",
        }.get(arch_host)

    if not arch:
        raise RecipeException("vcvars unsupported architectures %s-%s" % (arch_build, arch_host))

    return arch


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
    Returns the corresponding platform toolset based on the compiler setting.
    In case no toolset is configured in the profile, it will return a toolset based on the
    compiler version, otherwise, it will return the toolset from the profile.
    When there is no compiler version neither toolset configured, it will return None
    It supports msvc and clang compilers. For clang, it assumes the ClangCl toolset,
    as provided by the Visual Studio installer.

    :param recipe: Recipefile instance to access settings.compiler
    :return: A toolset when compiler.version is valid or compiler.toolset is configured. Otherwise, None.
    """
    settings = recipe.settings
    compiler = settings.compiler
    compiler_version = settings.compiler_version
    if compiler == "msvc":
        subs_toolset = settings.compiler_toolset
        if subs_toolset:
            return subs_toolset
        return msvc_version_to_toolset_version(compiler_version)
    if compiler == "clang":
        return "ClangCl"
