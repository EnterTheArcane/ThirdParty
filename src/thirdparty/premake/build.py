import jinja2
import textwrap
from pathlib import Path
from typing import Any, cast

from thirdparty.build.cpu import build_jobs
from thirdparty.errors import RecipeException
from thirdparty.files import save
from thirdparty.msbuild import MSBuild
from thirdparty.premake.constants import RECIPE_TO_PREMAKE_ARCH
from thirdparty.premake.toolchain import PremakeToolchain
from thirdparty.recipe import RecipeBase
from thirdparty.shell import run

# Source: https://learn.microsoft.com/en-us/cpp/overview/compiler-versions?view=msvc-170
PREMAKE_VS_VERSION = {
    "190": "2015", "191": "2017", "192": "2019", "193": "2022", "194": "2022",  # still 2022
    "195": "2026",
}


class Premake:
    """
    This class calls Premake commands when a package is being built. Notice that
    this one should be used together with the ``PremakeToolchain`` generator.

    This premake generator is only compatible with ``premake5``.
    """

    filename = "recipe.premake5.lua"

    # Recipe premake file which will preconfigure toolchain and then will call the user's premake file
    _premake_file_template = textwrap.dedent(
        """
        #!lua
        include("{{luafile}}")
        include("{{premake_recipe_toolchain}}")
        """)

    _recipe: RecipeBase
    luafile: str
    arguments: dict[str, Any]
    action: str

    def __init__(self, recipe: RecipeBase):
        """
        :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
        """
        self._recipe = recipe
        #: Path to the root premake5 lua file (default is ``premake5.lua``)
        self.luafile = (Path(self._recipe.folders.source) / "premake5.lua").as_posix()
        #: Key value pairs. Will translate to "--{key}={value}"
        self.arguments = {}  # https://premake.github.io/docs/Command-Line-Arguments/

        if "msvc" in cast(str, self._recipe.settings.compiler):
            msvc_version = PREMAKE_VS_VERSION.get(str(self._recipe.settings.compiler_version))
            self.action = f"vs{msvc_version}"
        else:
            self.action = "gmake"  # New generator (old gmakelegacy is deprecated)

        self._premake_recipe_toolchain = Path(self._recipe.folders.generators) / PremakeToolchain.filename

    @staticmethod
    def _expand_args(args: dict[str, Any]) -> str:
        return " ".join([f"--{key}={value}" for key, value in args.items()])

    def configure(self):
        """
        Runs ``premake5 <action> [FILE]`` which will generate respective build scripts depending on the ``action``.
        """
        if self._premake_recipe_toolchain.exists():
            content = jinja2.Template(self._premake_file_template).render(
                premake_recipe_toolchain=self._premake_recipe_toolchain.as_posix(), luafile=self.luafile)
            recipe_luafile = Path(self._recipe.folders.build) / self.filename
            save(self._recipe, recipe_luafile, content)
            arch = str(self._recipe.settings.arch)
            if arch not in RECIPE_TO_PREMAKE_ARCH:
                raise RecipeException(f"Premake does not support {arch} architecture.")
            self.arguments["arch"] = RECIPE_TO_PREMAKE_ARCH[arch]
        else:
            # Old behavior, for backward compatibility
            recipe_luafile = self.luafile

        premake_options: dict[str, Any] = dict()
        premake_options["file"] = f'"{recipe_luafile}"'

        premake_command = (f"premake5 {self._expand_args(premake_options)} {self.action} "
                           f"{self._expand_args(self.arguments)}{self._premake_verbosity}")
        run(self._recipe, premake_command)

    @property
    def _premake_verbosity(self):
        return " --verbose" if self._recipe.conf.tools.build.verbose else ""

    @property
    def _compilation_verbosity(self):
        verbosity = self._recipe.conf.tools.compilation.verbose
        # --verbose does not print compilation commands but internal Makefile progress logic
        return " verbose=1" if verbosity else ""

    def build(
        self,
        workspace: str,
        targets: list[str] | None = None,
        configuration: str | None = None,
        msbuild_platform: str | None = None):
        """
        Depending on the action, this method will run either ``msbuild`` or ``make`` with ``N_JOBS``.
        You can specify ``N_JOBS`` through the configuration line ``tools.build:jobs=N_JOBS``
        in your profile ``[conf]`` section.

        :param workspace: ``str`` Specifies the solution to be compiled (only used by ``MSBuild``).
        :param targets: ``List[str]`` Declare the projects to be built (None to build all projects).
        :param configuration: ``str`` Specify the configuration build type, default to build_type ("Release" or "Debug"),
            but this allow setting custom configuration type.
        :param msbuild_platform: ``str`` Specify the platform for the internal MSBuild generator (only used by ``MSBuild``).
        """
        if not self._premake_recipe_toolchain.exists():
            raise RecipeException("Premake.build() method requires PremakeToolchain to work properly")

        build_type = configuration or str(self._recipe.settings.build_type)
        if self.action.startswith("vs"):
            msbuild = MSBuild(self._recipe)
            if msbuild_platform:
                msbuild.platform = msbuild_platform
            msbuild.build_type = build_type
            msbuild.build(sln=f"{workspace}.sln", targets=targets)
        else:
            targets_str = "all" if targets is None else " ".join(targets)
            njobs = build_jobs(self._recipe)
            run(self._recipe, f"make config={build_type.lower()} {targets_str} -j{njobs}{self._compilation_verbosity}")
