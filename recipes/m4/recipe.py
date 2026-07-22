import os
import shutil

from thirdparty import RecipeBase
from thirdparty.build import cross_building
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import apply_patches, copy, get, rmdir, save
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.microsoft import is_msvc, unix_path
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "m4"
    version = "1.4.21"
    license = "GPL-3.0-only"

    def latest_version(self):
        repo = GithubRepository(self, "autotools-mirror/m4")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        if self.settings_build.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://ftpmirror.gnu.org/gnu/m4/m4-{self.version}.tar.xz",
            sha256="f25c6ab51548a73a75558742fb031e0625d6485fe5f9155949d6486a2408ab66",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = AutotoolsToolchain(self)
        if is_msvc(self):
            tc.extra_cflags.append("-FS")
            # Avoid a `Assertion Failed Dialog Box` during configure with build_type=Debug
            # Visual Studio does not support the %n format flag:
            # https://docs.microsoft.com/en-us/cpp/c-runtime-library/format-specification-syntax-printf-and-wprintf-functions
            # Because the %n format is inherently insecure, it is disabled by default. If %n is encountered in a format string,
            # the invalid parameter handler is invoked, as described in Parameter Validation. To enable %n support, see _set_printf_count_output.
            tc.configure_args.extend(
                [
                    "gl_cv_func_printf_directive_n=no",
                    "gl_cv_func_snprintf_directive_n=no",
                    "gl_cv_func_snprintf_directive_n=no",
                ])
            if self.settings.build_type in ("Debug", "RelWithDebInfo"):
                tc.extra_ldflags.append("-PDB")

        if cross_building(self) and is_msvc(self):
            triplet_arch_windows = {"X64": "x86_64", "ARM": "aarch64"}

            host_arch = triplet_arch_windows.get(str(self.settings.arch))
            build_arch = triplet_arch_windows.get(str(self.settings_build.arch))

            if host_arch and build_arch:
                host = f"{host_arch}-w64-mingw32"
                build = f"{build_arch}-w64-mingw32"
                tc.configure_args.extend(
                    [
                        f"--host={host}",
                        f"--build={build}",
                    ])
        if self.settings.os == "Windows":
            tc.configure_args.append("ac_cv_func__set_invalid_parameter_handler=yes")
        env = tc.environment()
        # help2man trick
        env.prepend_path("PATH", self.folders.source)
        # handle msvc
        if is_msvc(self):
            ar_wrapper = unix_path(self, self.folders.source / "build-aux" / "ar-lib")
            env.define("CC", "cl -nologo")
            env.define("CXX", "cl -nologo")
            env.define("AR", f"{ar_wrapper} lib")
            env.define("LD", "link")
            env.define("NM", "dumpbin -symbols")
            env.define("OBJDUMP", ":")
            env.define("RANLIB", ":")
            env.define("STRIP", ":")
        tc.generate(env)

    def build(self):
        self._patch_sources()
        autotools = Autotools(self)
        autotools.configure()
        # gnulib ships self-tests (SUBDIRS 'tests') that link a windows-utf8 manifest .res compiled by GNU windres.
        # windres only emits x64 objects, so linking the test exes against an ARM64 target fails with LNK1112.
        # The m4 binary itself does not need those tests, so restrict the build to the library and the tool.
        make_args = ["SUBDIRS='. lib src'"] if self.settings.os == "Windows" else None
        autotools.make(args=make_args)

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        autotools = Autotools(self)
        install_args = ["SUBDIRS='. lib src'"] if self.settings.os == "Windows" else None
        autotools.install(args=install_args)
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.libdirs = []
        self.info.includedirs = []

        # M4 environment variable is used by a lot of scripts as a way to override a hard-coded embedded m4 path
        bin_ext = ".exe" if self.settings.os == "Windows" else ""
        m4_bin = (self.folders.package / "bin" / f"m4{bin_ext}").as_posix()
        self.info.runenv.define_path("M4", m4_bin)
        self.info.buildenv.define_path("M4", m4_bin)

    def _patch_sources(self):
        apply_patches(self)
        if shutil.which("help2man") == None:
            # dummy file for configure
            help2man = self.folders.source / "help2man"
            save(self, help2man, "#!/usr/bin/env bash\n:")
            if os.name == "posix":
                os.chmod(help2man, os.stat(help2man).st_mode | 0o111)
