import os
from pathlib import Path
from typing import cast

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os, fix_apple_shared_install_name
from thirdparty.build import cross_building
from thirdparty.env import VirtualBuildEnv, VirtualRunEnv, Environment
from thirdparty.files import copy, get, rename, replace_in_file
from thirdparty.autotools import Autotools, AutotoolsDeps, AutotoolsToolchain
from thirdparty.scm import GnuFtp
from thirdparty.microsoft import is_msvc, unix_path
from thirdparty.scm import Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    threads: str


_Options.__possible_values__ = {"threads": ["posix", "solaris", "pth", "windows", "disabled"]}


class Recipe(RecipeBase[_Options]):
    name = "gettext"
    version = "1.0"
    # Some parts of the project are GPL-3.0-or-later and some are LGPL-2.1-or-later.
    # At this time, only libintl is packaged, which is licensed under the LGPL-2.1-or-later.
    # If you modify this package to include other portions of the library, please configure the license accordingly.
    # The licensing of the project is documented here: https://www.gnu.org/software/gettext/manual/gettext.html#Licenses
    license = "LGPL-2.1-or-later"

    def latest_version(self):
        repo = GnuFtp(self, "gettext")
        return Version(repo.latest_release)

    def configure(self):
        self.options.threads = {"Solaris": "solaris", "Windows": "windows"}.get(str(self.settings.os), "posix")

        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        self.requires("libiconv")
        if self.settings_build.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")
        if is_msvc(self) or self._is_clang_cl:
            self.requires_tool("automake")

    def source(self):
        get(
            self,
            url=f"https://ftpmirror.gnu.org/gnu/gettext/gettext-{self.version}.tar.gz",
            sha256="85d99b79c981a404874c02e0342176cf75c7698e2b51fe41031cf6526d974f1a",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        if not cross_building(self):
            VirtualRunEnv(self).generate(scope="build")

        tc = AutotoolsToolchain(self)
        tc.configure_args += [
            "HELP2MAN=/bin/true",
            "EMACS=no",
            "--disable-nls",
            "--disable-dependency-tracking",
            "--enable-relocatable",
            "--disable-c++",
            "--disable-java",
            "--disable-csharp",
            "--disable-libasprintf",
            "--disable-curses",
            "--disable-threads" if self.options.threads == "disabled" else ("--enable-threads=" + str(self.options.threads)),
            f"--with-libiconv-prefix={unix_path(self, self.dependencies["libiconv"].folders.package)}",
        ]

        if is_apple_os(self):
            # not guessed properly when cross-building
            tc.configure_args.append("gl_cv_func_access_slash_works=yes")

        if is_msvc(self) or self._is_clang_cl:
            target = None
            if self.settings.arch == "X64":
                target = "x86_64-w64-mingw32"
            elif self.settings.arch == "x86":
                target = "i686-w64-mingw32"

            if target is not None:
                tc.configure_args += [f"--host={target}", f"--build={target}"]

            if (str(self.settings.compiler) == "Visual Studio" and Version(self.settings.compiler_version) >= "12") or \
                    (str(self.settings.compiler) == "msvc" and Version(self.settings.compiler_version) >= "180"):
                tc.extra_cflags += ["-FS"]

            if cross_building(self) or self.settings.arch == "ARM":
                # override guesses with known good values from a native build
                tc.configure_args.extend(
                    [
                        "gl_cv_func_frexpl_works=yes",
                        "gl_cv_func_mbrtowc_empty_input=no",
                        "gl_cv_func_snprintf_truncation_c99=yes",
                        "gl_cv_func_printf_flag_zero=yes",
                        "gl_cv_func_printf_precision=yes",
                        "gl_cv_func_swprintf_works=yes",
                        "gl_cv_func_swprintf_C_locale_sans_EILSEQ=yes",
                    ])

            if self.settings.build_type == "Debug":
                # Skip checking for the 'n' printf format directly
                # in msvc, as it is known to not be available due to security concerns.
                # Skipping it avoids a GUI prompt during ./configure for a debug build
                # See https://github.com/recipe-io/recipe-center-index/issues/23698
                tc.configure_args.extend(
                    [
                        "gl_cv_func_printf_directive_n=no",
                    ])
        tc.make_args += ["-C", "intl"]
        env = tc.environment()
        if is_msvc(self) or self._is_clang_cl:
            def programs() -> tuple[str, str, str, str | None]:
                rc = None
                if self.settings.arch == "X64":
                    rc = "windres --target=pe-x86-64"
                elif self.settings.arch == "x86":
                    rc = "windres --target=pe-i386"
                if self._is_clang_cl:
                    return os.environ.get("CC", "clang-cl"), os.environ.get("AR", "llvm-lib"), os.environ.get("LD", "lld-link"), rc
                return "cl -nologo", "lib", "link", rc

            compile_wrapper = unix_path(self, cast("str | os.PathLike[str]", self.conf.tools.automake.compile_wrapper))
            ar_wrapper = unix_path(self, cast("str | os.PathLike[str]", self.conf.tools.automake.lib_wrapper))
            cc, ar, link, rc = programs()
            env.define("CC", f"{compile_wrapper} {cc}")
            env.define("CXX", f"{compile_wrapper} {cc}")
            env.define("LD", link)
            env.define("AR", f"{ar_wrapper} {ar}")
            env.define("NM", "dumpbin -symbols")
            env.define("RANLIB", ":")
            env.define("STRIP", ":")
            if rc is not None:
                env.define("RC", rc)
                env.define("WINDRES", rc)
        tc.generate(env)

        if is_msvc(self) or self._is_clang_cl:
            # Custom AutotoolsDeps for cl like compilers
            # workaround for upstream issue 12784
            includedirs: list[str] = []
            defines: list[str] = []
            libs: list[str] = []
            libdirs: list[str] = []
            linkflags: list[str] = []
            cxxflags: list[str] = []
            cflags: list[str] = []
            for dependency in self.dependencies.values():
                deps_cpp_info = dependency.info.aggregated_components()
                includedirs.extend(deps_cpp_info.includedirs)
                defines.extend(deps_cpp_info.defines)
                libs.extend(deps_cpp_info.libs + deps_cpp_info.system_libs)
                libdirs.extend(deps_cpp_info.libdirs)
                linkflags.extend(deps_cpp_info.sharedlinkflags + deps_cpp_info.exelinkflags)
                cxxflags.extend(deps_cpp_info.cxxflags)
                cflags.extend(deps_cpp_info.cflags)

            env = Environment()
            env.append("CPPFLAGS", [f"-I{unix_path(self, p)}" for p in includedirs] + [f"-D{d}" for d in defines])
            env.append("_LINK_", [lib if lib.endswith(".lib") else f"{lib}.lib" for lib in libs])
            env.append("LDFLAGS", [f"-L{unix_path(self, p)}" for p in libdirs] + linkflags)
            env.append("CXXFLAGS", cxxflags)
            env.append("CFLAGS", cflags)
            env.vars(self).save_script("autotoolsdeps_cl_workaround")
        else:
            deps = AutotoolsDeps(self)
            deps.generate()

    def build(self):
        autotools = Autotools(self)
        autotools.configure("gettext-runtime")
        if self.settings.os == "Windows" and self.settings.arch == "ARM":
            # GNU windres cannot emit ARM64 objects, so the compiled libintl version
            # resource is an x64 object and fails to link (LNK1112). Drop the cosmetic
            # resource from libintl on ARM64.
            replace_in_file(
                self, self.folders.build / "intl" / "Makefile",
                "WOE32_LIBADD = libintl.res.lo", "WOE32_LIBADD =", strict=False)
        autotools.make()

    def package(self):
        dest_lib_dir = self.folders.package / "lib"
        dest_runtime_dir = self.folders.package / "bin"
        dest_include_dir = self.folders.package / "include"
        copy(self, "COPYING", self.folders.source, self.folders.package / "licenses")
        copy(self, "*gnuintl*.dll", self.folders.build, dest_runtime_dir, keep_path=False)
        copy(self, "*gnuintl*.lib", self.folders.build, dest_lib_dir, keep_path=False)
        copy(self, "*gnuintl*.a", self.folders.build, dest_lib_dir, keep_path=False)
        copy(self, "*gnuintl*.so*", self.folders.build, dest_lib_dir, keep_path=False)
        copy(self, "*gnuintl*.dylib", self.folders.build, dest_lib_dir, keep_path=False)
        copy(self, "*libgnuintl.h", self.folders.build, dest_include_dir, keep_path=False)
        rename(self, dest_include_dir / "libgnuintl.h", dest_include_dir / "libintl.h")
        fix_msvc_libname(self)
        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.set_property("cmake_file_name", "Intl")
        self.info.set_property("cmake_target_name", "Intl::Intl")
        self.info.set_property("cmake_target_aliases", ["gettext::gettext"])
        self.info.set_property("pkg_config_name", "gettext")
        self.info.libs = ["gnuintl"]
        if is_apple_os(self):
            self.info.frameworks.append("CoreFoundation")

    @property
    def _is_clang_cl(self):
        return self.settings.os == "Windows" \
            and self.settings.compiler == "clang" \
            and self.settings.compiler_runtime

    @property
    def _gettext_folder(self):
        return "gettext-tools"


def fix_msvc_libname(recipe: RecipeBase, remove_lib_prefix: bool = True):
    """remove lib prefix & change extension to .lib in case of cl like compiler"""
    if not recipe.settings.compiler_runtime:
        return
    libdirs = recipe.info.libdirs
    for libdir in libdirs:
        for ext in [".dll.a", ".dll.lib", ".a"]:
            full_folder: Path = recipe.folders.package / libdir
            for filepath in full_folder.glob(f"*{ext}"):
                libname = os.path.basename(filepath)[0:-len(ext)]
                if remove_lib_prefix and libname[0:3] == "lib":
                    libname = libname[3:]
                dst = filepath.parent / f"{libname}.lib"
                if os.path.isfile(dst):
                    os.remove(dst)
                rename(recipe, filepath, dst)
