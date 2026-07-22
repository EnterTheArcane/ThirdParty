import os
import re
import shutil

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os, fix_apple_shared_install_name
from thirdparty.env import Environment, VirtualBuildEnv
from thirdparty.errors import RecipeException
from thirdparty.files import apply_patches, copy, get, rename, replace_in_file, rmdir
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.scm import GnuFtp
from thirdparty.microsoft import is_msvc, unix_path
from thirdparty.scm import Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libtool"
    version = "2.6.2"
    license = "GPL-2.0-or-later", "GPL-3.0-or-later"

    _SOURCE_SHA256 = "24adb3aa9ae035c70faba344af57d73215eb89281045af6c7ccd307751f8b0bf"

    def latest_version(self):
        repo = GnuFtp(self, "libtool")
        return Version(repo.latest_release)

    def requirements(self):
        self.requires_tool("automake")
        self.requires_tool("gnu-config")
        self.requires_tool("m4")  # Needed by configure
        self.requires("automake")
        if self.settings_build.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://ftpmirror.gnu.org/libtool/libtool-{self.version}.tar.gz",
            sha256=self._SOURCE_SHA256,
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        if is_msvc(self):
            # __VSCMD_ARG_NO_LOGO: this test_package has too many invocations,
            #                      this avoids printing the logo everywhere
            # VSCMD_SKIP_SENDTELEMETRY: avoid the telemetry process holding onto the directory
            #                           unnecessarily
            env = Environment()
            env.define("__VSCMD_ARG_NO_LOGO", "1")
            env.define("VSCMD_SKIP_SENDTELEMETRY", "1")
            env.vars(self, scope="build").save_script("buildenv_vcvars_options.bat")

        tc = AutotoolsToolchain(self)
        tc.configure_args.extend(
            [
                "--datarootdir=${prefix}/res",
                "--enable-shared",
                "--enable-static",
                "--enable-ltdl-install",
            ])

        env = tc.environment()
        if is_msvc(self):
            ar_wrapper = self.dependencies.build["automake"].info.conf.tools.automake.lib_wrapper
            ar_wrapper = unix_path(self, ar_wrapper)
            env.define("CC", "cl -nologo")
            env.define("CXX", "cl -nologo")
            env.define("AR", f'{ar_wrapper} "lib -nologo"')

            # Disable Fortran detection to handle issue with VS 2022
            # See: https://savannah.gnu.org/patch/?9313#comment1
            # In the future this could be removed if a new version fixes this
            # upstream
            env.define("F77", "no")
            env.define("FC", "no")
        tc.generate(env)

    def build(self):
        self._patch_sources()
        autotools = Autotools(self)
        autotools.configure()
        autotools.make()

    def package(self):
        copy(self, "COPYING*", src=self.folders.source, dst=self.folders.package / "licenses")
        autotools = Autotools(self)
        autotools.install()
        fix_apple_shared_install_name(self)

        rmdir(self, self._datarootdir / "info")
        rmdir(self, self._datarootdir / "man")

        os.unlink(self.folders.package / "lib" / "libltdl.la")
        if self.options.shared:
            self._rm_binlib_files_containing(self._static_ext, self._shared_ext)
        else:
            self._rm_binlib_files_containing(self._shared_ext)

        files = (
            self.folders.package / "bin" / "libtool",
            self.folders.package / "bin" / "libtoolize",
        )
        replaces = {
            "GREP": "/usr/bin/env grep",
            "EGREP": "/usr/bin/env grep -E",
            "FGREP": "/usr/bin/env grep -F",
            "SED": "/usr/bin/env sed",
        }
        for file in files:
            contents = open(file).read()
            for key, repl in replaces.items():
                contents, nb1 = re.subn("^{}=\"[^\"]*\"".format(key), "{}=\"{}\"".format(key, repl), contents, flags=re.MULTILINE)
                contents, nb2 = re.subn("^: \\$\\{{{}=\"[^$\"]*\"\\}}".format(key), ": ${{{}=\"{}\"}}".format(key, repl), contents, flags=re.MULTILINE)
                if nb1 + nb2 == 0:
                    raise RecipeException(f"Failed to find {key} in {repl}")
            open(file, "w").write(contents)

        binpath = self.folders.package / "bin"
        if self.settings.os == "Windows":
            rename(
                self, binpath / "libtoolize",
                binpath / "libtoolize.exe")
            rename(
                self, binpath / "libtool",
                binpath / "libtool.exe")

        if is_msvc(self) and self.options.shared:
            rename(
                self, self.folders.package / "lib" / "ltdl.dll.lib",
                self.folders.package / "lib" / "ltdl.lib")

        # allow libtool to link static libs into shared for more platforms
        libtool_m4 = self._datarootdir / "aclocal" / "libtool.m4"
        method_pass_all = "lt_cv_deplibs_check_method=pass_all"
        replace_in_file(
            self, libtool_m4,
            "lt_cv_deplibs_check_method='file_magic ^x86 archive import|^x86 DLL'",
            method_pass_all)
        replace_in_file(
            self, libtool_m4,
            "lt_cv_deplibs_check_method='file_magic file format (pei*-i386(.*architecture: i386)?|pe-arm-wince|pe-x86-64|pe-aarch64)'",
            method_pass_all)

    def package_info(self):
        self.info.libs = ["ltdl"]

        if self.options.shared:
            if self.settings.os == "Windows":
                self.info.defines = ["LIBLTDL_DLL_IMPORT"]
        else:
            if self.settings.os == "Linux":
                self.info.system_libs = ["dl"]

        # Define environment variables such that libtool m4 files are seen by Automake
        libtool_aclocal_dir = self._datarootdir / "aclocal"

        self.info.buildenv.append_path("ACLOCAL_PATH", libtool_aclocal_dir)
        self.info.buildenv.append_path("AUTOMAKE_RECIPE_INCLUDES", libtool_aclocal_dir)
        self.info.runenv.append_path("ACLOCAL_PATH", libtool_aclocal_dir)
        self.info.runenv.append_path("AUTOMAKE_RECIPE_INCLUDES", libtool_aclocal_dir)

    @property
    def _datarootdir(self):
        return self.folders.package / "res"

    def _patch_sources(self):
        apply_patches(self)
        config_guess = self.dependencies.build["gnu-config"].info.conf.tools.gnu_config.config_guess
        config_sub = self.dependencies.build["gnu-config"].info.conf.tools.gnu_config.config_sub
        shutil.copy(config_sub, self.folders.source / "build-aux" / "config.sub")
        shutil.copy(config_guess, self.folders.source / "build-aux" / "config.guess")

    @property
    def _shared_ext(self):
        if self.settings.os == "Windows":
            return "dll"
        elif is_apple_os(self):
            return "dylib"
        else:
            return "so"

    @property
    def _static_ext(self):
        if is_msvc(self):
            return "lib"
        else:
            return "a"

    def _rm_binlib_files_containing(self, ext_inclusive: str, ext_exclusive: str | None = None):
        regex_in = re.compile(r".*\.({})($|\..*)".format(ext_inclusive))
        if ext_exclusive:
            regex_out = re.compile(r".*\.({})($|\..*)".format(ext_exclusive))
        else:
            regex_out = re.compile("^$")
        for directory in (
                self.folders.package / "bin",
                self.folders.package / "lib",
        ):
            for file in os.listdir(directory):
                if regex_in.match(file) and not regex_out.match(file):
                    os.unlink(os.path.join(directory, file))
