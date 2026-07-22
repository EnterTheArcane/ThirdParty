
from typing import cast

from thirdparty.build.flags import build_type_flags, cppstd_flag, build_type_link_flags
from thirdparty.env import Environment
from thirdparty.nmake.deps import format_defines
from thirdparty.microsoft.visual import msvc_runtime_flag, VCVars
from thirdparty.recipe import RecipeBase


class NMakeToolchain:
    """
    https://learn.microsoft.com/en-us/cpp/build/reference/running-nmake?view=msvc-170#toolsini-and-nmake
    We have also explored the usage of Tools.ini:
    https://learn.microsoft.com/en-us/cpp/build/reference/running-nmake?view=msvc-170
    but not possible, because it cannot include other files, it will also potentially collide with
    a user Tool.ini, without easy resolution. At least the environment is additive.
    """

    _recipe: RecipeBase
    extra_cflags: list[str]
    extra_cxxflags: list[str]
    extra_ldflags: list[str]
    extra_defines: list[str]

    def __init__(self, recipe: RecipeBase):
        """
        :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
        """
        self._recipe = recipe

        # Flags
        self.extra_cflags = []
        self.extra_cxxflags = []
        self.extra_ldflags = []
        self.extra_defines = []

    @staticmethod
    def _format_options(options: list[str]) -> list[str]:
        return [f"{opt[0].replace("-", "/")}{opt[1:]}" for opt in options if len(opt) > 1]

    @property
    def _arch_defines(self) -> list[str]:
        # Recent Windows SDK headers still check these target macros in some
        # NMake/MSVC flows, but vcvarsall doesn't always seed them into CL.
        arch = self._recipe.settings.arch
        return {
            "X86": ["_X86_"],
            "X64": ["_AMD64_"],
            "ARM": ["_ARM64_"],
        }.get(arch, [])

    @property
    def _cl(self):
        bt_flags = build_type_flags(self._recipe)
        bt_flags = bt_flags if bt_flags else []

        rt_flags = msvc_runtime_flag(self._recipe)
        rt_flags = [f"/{rt_flags}"] if rt_flags else []

        cflags: list[str] = []
        cflags.extend(self._recipe.conf.tools.build.cflags)
        cflags.extend(self.extra_cflags)

        cxxflags: list[str] = []
        cppstd = cppstd_flag(self._recipe)
        if cppstd:
            cxxflags.append(cppstd)
        cxxflags.extend(self._recipe.conf.tools.build.cxxflags)
        cxxflags.extend(self.extra_cxxflags)

        defines: list[str] = []
        build_type = self._recipe.settings.build_type
        if build_type in ["Release", "RelWithDebInfo", "MinSizeRel"]:
            defines.append("NDEBUG")
        defines.extend(self._arch_defines)
        defines.extend(self._recipe.conf.tools.build.defines)
        defines.extend(self.extra_defines)

        return (["/nologo"] + self._format_options(bt_flags + rt_flags + cflags + cxxflags) + format_defines(defines, toolchain=True))

    @property
    def _link(self):
        bt_ldflags = build_type_link_flags(self._recipe.settings)
        bt_ldflags = bt_ldflags if bt_ldflags else []

        ldflags: list[str] = []
        ldflags.extend(bt_ldflags)
        ldflags.extend(self._recipe.conf.tools.build.sharedlinkflags)
        ldflags.extend(self._recipe.conf.tools.build.exelinkflags)
        ldflags.extend(self.extra_ldflags)

        return ["/nologo"] + self._format_options(ldflags)

    @property
    def _rcflags(self):
        rcflags = self._recipe.conf.tools.build.rcflags
        return self._format_options(rcflags) if rcflags else []

    def environment(self):
        env = Environment()
        # Injection of compile flags in CL env-var:
        # https://learn.microsoft.com/en-us/cpp/build/reference/cl-environment-variables
        env.append("CL", self._cl)
        # Injection of link flags in _LINK_ env-var:
        # https://learn.microsoft.com/en-us/cpp/build/reference/linking
        env.append("_LINK_", self._link)
        if self._rcflags:
            env.append("RCFLAGS", self._rcflags)
        # Also define some special env-vars which can override special NMake macros:
        # https://learn.microsoft.com/en-us/cpp/build/reference/special-nmake-macros
        conf_compilers = self._recipe.conf.tools.build.compiler_executables
        if conf_compilers:
            compilers_mapping = {
                "AS": "asm", "CC": "c", "CPP": "cpp", "CXX": "cpp", "RC": "rc",
            }
            for env_var, comp in compilers_mapping.items():
                if comp in conf_compilers:
                    env.define(env_var, cast(str, conf_compilers[comp]))
        return env

    def vars(self):
        return self.environment().vars(self._recipe, scope="build")

    def generate(self, env: Environment | None = None, scope: str = "build"):
        env = env or self.environment()
        env.vars(self._recipe, scope=scope).save_script("nmaketoolchain")
        VCVars(self._recipe).generate(scope=scope)
