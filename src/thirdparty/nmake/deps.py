import os
from typing import cast

from thirdparty import Info
from thirdparty.env import Environment
from thirdparty.recipe import RecipeBase


def format_defines(defines: list[str], toolchain: bool = False) -> list[str]:
    def is_hex_or_numeric(s: str) -> bool:
        try:
            # Check for Hexadecimal (base 16)
            int(s, 16)
            return True
        except ValueError:
            return False

    formated_defines: list[str] = []
    for define in defines:
        if "=" in define:
            # CL env-var can't accept '=' sign in /D option, it can be replaced by '#' sign:
            # https://learn.microsoft.com/en-us/cpp/build/reference/cl-environment-variables
            macro, value = define.split("=", 1)
            if value and not is_hex_or_numeric(value):
                # value quotes are escaped
                value = f'\\"{value}\\"' if toolchain else f'\"{value}\"'
            define = f"{macro}#{value}"
        formated_defines.append(f'/D"{define}"')
    return formated_defines


class NMakeDeps:
    def __init__(self, recipe: RecipeBase):
        """
        :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
        """
        self._recipe = recipe
        self._environment = None

    # TODO: This is similar from AutotoolsDeps: Refactor and make common
    def _get_cpp_info(self) -> Info:
        ret = Info()
        deps = self._recipe.dependencies.host.topological_sort
        deps = [dep for dep in reversed(deps.values())]
        for dep in deps:
            dep_cppinfo = dep.info.aggregated_components()
            # In case we have components, aggregate them, we do not support isolated
            # "targets" with autotools
            ret.merge(dep_cppinfo)
        return ret

    @property
    def environment(self):
        # TODO: Seems we want to make this uniform, equal to other generators
        if self._environment is None:
            info = self._get_cpp_info()

            lib_paths = ";".join(info.libdirs or [])

            def format_lib(lib: str) -> str:
                ext = os.path.splitext(lib)[1]
                return lib if ext in (".so", ".lib", ".a", ".dylib", ".bc") else "%s.lib" % lib

            ret: list[str] = []
            ret.extend(info.exelinkflags or [])
            ret.extend(info.sharedlinkflags or [])
            ret.extend([format_lib(lib) for lib in cast("list[str]", info.libs or [])])
            ret.extend([format_lib(lib) for lib in cast("list[str]", info.system_libs or [])])
            link_args = " ".join(ret)

            cl_flags = [f'-I"{p}"' for p in cast("list[str]", info.includedirs or [])]
            cl_flags.extend(info.cflags or [])
            cl_flags.extend(info.cxxflags or [])
            cl_flags.extend(format_defines(info.defines or []))

            env = Environment()
            env.append("CL", " ".join(cl_flags))
            env.append_path("LIB", lib_paths)
            env.append("_LINK_", link_args)
            self._environment = env
        return self._environment

    def vars(self, scope: str = "build"):
        return self.environment.vars(self._recipe, scope=scope)

    def generate(self, scope: str = "build"):
        self.vars(scope).save_script("nmakedeps")
