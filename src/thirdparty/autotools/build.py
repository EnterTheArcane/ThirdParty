import os
from pathlib import Path
import re
from collections.abc import Iterable
from typing import cast

from thirdparty._internal.subsystems import subsystem_path, deduce_subsystem
from thirdparty.build import build_jobs, cmd_args_to_string, load_toolchain_args
from thirdparty.files import chdir
from thirdparty.microsoft import unix_path
from thirdparty.recipe import RecipeBase
from thirdparty.shell import run


def join_arguments(args: Iterable[str | None]) -> str:
    return " ".join(filter(None, args))


class Autotools:
    _recipe: RecipeBase
    _configure_args: str | None
    _make_args: str | None
    _autoreconf_args: str | None

    def __init__(self, recipe: RecipeBase, namespace: str | None = None):
        """
        :param recipe: The current recipe object. Always use ``self``.
        :param namespace: this argument avoids collisions when you have multiple toolchain calls in
                          the same recipe. By setting this argument, the *buildenv.conf* file used
                          to pass information to the toolchain will be named as:
                          *<namespace>_buildenv.conf*. The default value is ``None`` meaning that
                          the name of the generated file is *buildenv.conf*. This namespace must
                          be also set with the same value in the constructor of the AutotoolsToolchain
                          so that it reads the information from the proper file.
        """
        self._recipe = recipe

        toolchain_file_content = load_toolchain_args(
            os.fspath(self._recipe.folders.generators), namespace=namespace)

        self._configure_args = toolchain_file_content.get("configure_args")
        self._make_args = toolchain_file_content.get("make_args")
        self._autoreconf_args = toolchain_file_content.get("autoreconf_args")

    def configure(
            self,
            build_script_folder: str | Path | None = None,
            args: list[str] | None = None):
        """
        Call the configure script.

        :param args: List of arguments to use for the ``configure`` call.
        :param build_script_folder: Subfolder where the `configure` script is located. If not specified
                                    recipe.folders.source is used.
        """
        # http://jingfenghanmax.blogspot.com.es/2010/09/configure-with-host-target-and-build.html
        # https://gcc.gnu.org/onlinedocs/gccint/Configure-Terms.html
        script_folder = self._recipe.folders.source / build_script_folder if build_script_folder else self._recipe.folders.source

        configure_args: list[str] = []
        configure_args.extend(args or [])

        self._configure_args = f"{self._configure_args} {cmd_args_to_string(configure_args)}"

        configure_cmd = script_folder / "configure"
        subsystem = deduce_subsystem(self._recipe, scope="build")
        configure_cmd = subsystem_path(subsystem, configure_cmd)
        cmd = f'"{configure_cmd}" {self._configure_args}'
        run(self._recipe, cmd)

    def make(
        self, target: str | None = None, args: list[str] | None = None, makefile: str | None = None):
        """
        Call the make program.

        :param target: (Optional, Defaulted to ``None``): Choose which target to build. This allows
                       building of e.g., docs, shared libraries or install for some AutoTools
                       projects
        :param args: (Optional, Defaulted to ``None``): List of arguments to use for the
                     ``make`` call.
        :param makefile: (Optional, Defaulted to ``None``): Allow specifying a custom makefile to use instead of default "Makefile"
        """
        make_program = self._recipe.conf.tools.gnu.make_program or ("mingw32-make" if self._use_win_mingw() else "make")
        subsystem = deduce_subsystem(self._recipe, scope="build")
        make_program = subsystem_path(subsystem, make_program)
        str_args = self._make_args
        str_extra_args = " ".join(args) if args is not None else ""
        jobs = ""
        jobs_already_passed = re.search(r"(^-j\d+)|(\W-j\d+\s*)", join_arguments([str_args, str_extra_args]))
        if not jobs_already_passed and "nmake" not in make_program.lower():
            njobs = build_jobs(self._recipe)
            if njobs:
                jobs = f"-j{njobs}"
        str_makefile = f"--file={makefile}" if makefile else None

        # Quiet builds: `-s` silences make's own command echo (so makefiles that don't support
        # automake silent rules, e.g. icu/libvpx, stop dumping the full compiler command per file),
        # and `V=0` additionally selects automake's terse "CC foo.o" rules. Both leave warnings and
        # errors intact. nmake doesn't use either.
        silent = None
        if "nmake" not in make_program.lower() and not self._recipe.conf.tools.compilation.verbose:
            silent = "-s V=0"

        command = join_arguments([make_program, str_makefile, target, str_args, str_extra_args, jobs, silent])
        run(self._recipe, command)

    def install(
        self, args: list[str] | None = None, target: str | None = None, makefile: str | None = None):
        """
        This is just an "alias" of ``self.make(target="install")`` or ``self.make(target="install-strip")``

        :param args: (Optional, Defaulted to ``None``): List of arguments to use for the
                     ``make`` call. By default an argument ``DESTDIR=unix_path(self.folders.package)``
                     is added to the call if the passed value is ``None``. See more information about
                     :ref:`tools.microsoft.unix_path() function<recipe_tools_microsoft_unix_path>`
        :param target: (Optional, Defaulted to ``None``): Choose which target to install.
        :param makefile: (Optional, Defaulted to ``None``): Allow specifying a custom makefile to use instead of default "Makefile"
        """
        if target is None:
            target = "install"
            install_strip = self._recipe.conf.tools.build.install_strip
            do_strip = install_strip if isinstance(install_strip, bool) else "autotools" in (install_strip or [])
            if do_strip:
                target += "-strip"
        args = args if args else []
        str_args = " ".join(args)
        if "DESTDIR=" not in str_args:
            args.insert(0, f"DESTDIR={unix_path(self._recipe, self._recipe.folders.package)}")
        self.make(target=target, args=args, makefile=makefile)

    def autoreconf(self, build_script_folder: str | None = None, args: list[str] | None = None):
        """
        Call ``autoreconf``

        :param args: (Optional, Defaulted to ``None``): List of arguments to use for the
                     ``autoreconf`` call.
        :param build_script_folder: Subfolder where the `configure` script is located. If not specified
                                    recipe.folders.source is used.
        """
        script_folder = os.path.join(self._recipe.folders.source, build_script_folder) if build_script_folder else self._recipe.folders.source
        args = args or []
        command = join_arguments(["autoreconf", self._autoreconf_args, cmd_args_to_string(args)])
        with chdir(cast(RecipeBase, self), script_folder):
            run(self._recipe, command)

    def _use_win_mingw(self) -> bool:
        os_build = self._recipe.settings_build.os

        if os_build == "Windows":
            compiler = self._recipe.settings.compiler
            sub = self._recipe.settings.os_subsystem
            if sub == "msys2" or compiler == "qcc":
                return False
            else:
                if self._recipe.win_bash:
                    return False
                return True
        return False
