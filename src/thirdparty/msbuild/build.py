import os

from thirdparty.errors import RecipeException
from thirdparty.microsoft.visual import msvc_platform_from_arch
from thirdparty.recipe import RecipeBase
from thirdparty.shell import run


def msbuild_verbosity_cmd_line_arg(recipe: RecipeBase) -> str:
    """
    Controls msbuild verbosity.
    See https://learn.microsoft.com/en-us/visualstudio/msbuild/msbuild-command-line-reference
    :return:
    """
    level = "Detailed" if recipe.conf.tools.build.verbose else "Quiet"
    return f"-verbosity:{level}"


class MSBuild:
    """
    MSBuild build helper class
    """

    _recipe: RecipeBase
    build_type: str | None
    platform: str | None

    def __init__(self, recipe: RecipeBase):
        """
        :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
        """
        self._recipe = recipe
        #: Defines the build type. By default, ``settings.build_type``.
        self.build_type = recipe.settings.build_type
        # if platforms:
        #    msvc_arch.update(platforms)
        arch = recipe.settings.arch
        # MSVC default platform for VS projects is "x86", not "Win32" (but CMake default is "Win32")
        msvc_platform = msvc_platform_from_arch(arch) if arch != "x86" else "x86"
        #: Defines the platform name, e.g., ``ARM`` if ``settings.arch == "armv7"``.
        self.platform = msvc_platform

    def command(self, sln: str | os.PathLike[str], targets: list[str] | None = None) -> str:
        """
        Gets the ``msbuild`` command line. For instance,
        :command:`msbuild.exe "MyProject.sln" -p:Configuration=<conf> -p:Platform=<platform>`.

        :param sln: ``str`` name of Visual Studio ``*.sln`` file
        :param targets: ``targets`` is an optional argument, defaults to ``None``, and otherwise it is a list of targets to build
        :return: ``str`` msbuild command line.
        """
        # TODO: Enable output_binary_log via config
        cmd = ('msbuild.exe "%s" -p:Configuration="%s" -p:Platform="%s"' % (sln, self.build_type, self.platform))

        verbosity = msbuild_verbosity_cmd_line_arg(self._recipe)
        if verbosity:
            cmd += f" {verbosity}"

        maxcpucount = self._recipe.conf.tools.msbuild.max_cpu_count
        if maxcpucount is not None:
            cmd += f' -m:"{maxcpucount}"' if maxcpucount > 0 else " -m"

        if targets:
            if not isinstance(targets, list):  # pyright: ignore[reportUnnecessaryIsInstance]  # defensive: recipes may pass a non-list
                raise RecipeException("targets argument should be a list")
            cmd += f' -target:"{";".join(targets)}"'

        return cmd

    def build(self, sln: str | os.PathLike[str], targets: list[str] | None = None):
        """
        Runs the ``msbuild`` command line obtained from ``self.command(sln)``.

        :param sln: ``str`` name of Visual Studio ``*.sln`` file
        :param targets: ``targets`` is an optional argument, defaults to ``None``, and otherwise it is a list of targets to build
        """
        cmd = self.command(sln, targets=targets)
        run(self._recipe, cmd)

    @staticmethod
    def get_version(_):
        return NotImplementedError(
            "get_version() method is not supported in MSBuild "
            "toolchain helper")
