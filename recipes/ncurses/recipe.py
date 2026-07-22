import os
from typing import Any, Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name
from thirdparty.build import cross_building, stdcpp_library
from thirdparty.env import Environment, VirtualBuildEnv
from thirdparty.files import copy, get, replace_in_file
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.microsoft import is_msvc, unix_path
from thirdparty.scm import GnuFtp, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    with_widec: bool = True
    with_extended_colors: bool = True
    with_cxx: bool = True
    with_progs: bool = True
    with_ticlib: Literal["auto", True, False] = "auto"
    with_reentrant: bool = False
    with_tinfo: Literal["auto", True, False] = "auto"
    with_pcre2: bool = False


class Recipe(RecipeBase[_Options]):
    name = "ncurses"
    version = "6.6"
    license = "X11"

    def latest_version(self):
        return Version(GnuFtp(self, "ncurses").latest_release)

    def configure(self):
        # Set the default value based on OS
        self.options.with_ticlib = self.settings.os != "Windows"
        self.options.with_tinfo = self.settings.os != "Windows"

        if not self.options.with_cxx:
            self.settings.compiler_libcxx = None
            self.settings.compiler_cxx_standard = None
        if not self.options.with_widec:
            self.options.with_extended_colors = False

    def requirements(self):
        if self.options.with_pcre2:
            self.requires("pcre2")
        if is_msvc(self):
            self.requires("getopt-for-visual-studio")
            self.requires("dirent")
            if self.options.with_extended_colors:
                self.requires("naive-tsearch")
        if self.settings_build.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://ftpmirror.gnu.org/gnu/ncurses/ncurses-{self.version}.tar.gz",
            sha256="355b4cbbed880b0381a04c46617b7656e362585d52e9cf84a67e2009b749ff11",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = AutotoolsToolchain(self)
        
        def yes_no(v: Any) -> str:
            return "yes" if v else "no"
        
        tc.configure_args += [
            f"--with-shared={yes_no(self.options.shared)}",
            f"--with-cxx-shared={yes_no(self.options.shared)}",
            f"--with-normal={yes_no(not self.options.shared)}",
            f"--enable-widec={yes_no(self.options.with_widec)}",
            f"--enable-ext-colors={yes_no(self.options.with_extended_colors)}",
            f"--enable-reentrant={yes_no(self.options.with_reentrant)}",
            f"--with-pcre2={yes_no(self.options.with_pcre2)}",
            f"--with-cxx-binding={yes_no(self.options.with_cxx)}",
            f"--with-progs={yes_no(self.options.with_progs)}",
            f"--with-termlib={yes_no(self.options.with_tinfo)}",
            f"--with-ticlib={yes_no(self.options.with_ticlib)}",
            "--without-libtool",
            "--without-ada",
            "--without-manpages",
            "--without-tests",
            "--disable-echo",
            "--without-debug",
            "--without-profile",
            "--with-sp-funcs",
            "--disable-rpath",
            "--disable-pc-files",
            "--datarootdir=${prefix}/res",
        ]
        if cross_building(self):
            # `install -s` strips with the build machine's strip, which cannot process
            # target-arch executables (e.g. x64 strip on an ARM64 tic.exe reports
            # "file format not recognized"). Skip stripping when cross-compiling.
            tc.configure_args.append("--disable-stripping")
        build = None
        host = None
        if self.settings.os == "Windows":
            tc.configure_args += [
                "--disable-macros",
                "--disable-termcap",
                "--enable-database",
                "--enable-sp-funcs",
                "--enable-term-driver",
                "--enable-interop",
            ]
        if is_msvc(self):
            build = host = f"{self.settings.arch}-w64-mingw32-msvc"
            tc.configure_args += [
                "ac_cv_func_getopt=yes",
                "ac_cv_func_setvbuf_reversed=no",
            ]
            # The env vars below are used by ./configure, but not during make
            tc.make_args += [
                "CC=cl -nologo",
                "CPP=cl -nologo -E",
            ]
            tc.extra_cflags.append("-FS")
            tc.extra_cxxflags.append("-FS")
            tc.extra_cxxflags.append("-EHsc")
            if self.options.with_extended_colors:
                tc.extra_cflags.append(" ".join(f"-I{dir}" for dir in self.dependencies["naive-tsearch"].info.includedirs))
                tc.extra_ldflags.append(" ".join(f"-l{lib}" for lib in self.dependencies["naive-tsearch"].info.libs))
        if self._is_mingw:
            # add libssp (gcc support library) for some missing symbols (e.g. __strcpy_chk)
            tc.extra_ldflags.extend(["-lmingwex", "-lssp"])
        if build:
            tc.configure_args.append(f"ac_cv_build={build}")
        if host:
            tc.configure_args.append(f"ac_cv_host={host}")
            tc.configure_args.append(f"ac_cv_target={host}")
        if self.settings.compiler == "gcc" and Version(self.settings.compiler_version) >= 15:
            # FIXME: Workaround to allow building with with GCC15
            # Upstream has proper but huge patches: https://invisible-island.net/ncurses/NEWS.html#index-t20241207
            tc.extra_cflags.append("-std=gnu17")

        # Allow ncurses to set the include dir with an appropriate subdir
        tc.configure_args.remove("--includedir=${prefix}/include")
        tc.generate()

        if is_msvc(self):
            env = Environment()
            env.define("CC", "cl -nologo -FS")
            env.define("CXX", "cl -nologo -FS")
            env.define("LD", "link")
            env.define("AR", "lib")
            env.define("NM", "dumpbin -symbols")
            env.define("OBJDUMP", ":")
            env.define("RANLIB", ":")
            env.define("STRIP", ":")
            env.vars(self).save_script("buildenv_msvc")

        if is_msvc(self):
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

        deps = PkgConfigDeps(self)
        deps.generate()

    def build(self):
        autotools = Autotools(self)
        autotools.configure()
        if is_msvc(self):
            # ncurses builds host tools (make_keys/make_hash) with BUILD_CC (gcc when
            # cross-compiling), compiling the library's generated names.c. Those variable
            # definitions are decorated __declspec(dllimport) unless NCURSES_STATIC is
            # defined -- MSVC only warns, but gcc errors ("definition is marked dllimport").
            # Host tools are never DLLs, so force NCURSES_STATIC into BUILD_CPPFLAGS.
            for root, _, files in os.walk(self.folders.build):
                if "Makefile" in files:
                    replace_in_file(
                        self, os.path.join(root, "Makefile"),
                        "-DUSE_BUILD_CC", "-DUSE_BUILD_CC -DNCURSES_STATIC", strict=False)
        autotools.make()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        autotools = Autotools(self)
        autotools.install()
        os.unlink(self.folders.package / "bin" / f"ncurses{self._suffix}{Version(self.version).major}-config")
        copy(
            self, "*.cmake",
            src=self.folders.recipe / "cmake",
            dst=self.folders.package / self._module_subfolder)
        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.set_property("cmake_file_name", "Curses")

        # CMake's standard FindCurses module does not define a target.
        # Adding one nevertheless for consistency with other packages.
        # https://gitlab.kitware.com/cmake/cmake/-/issues/23051
        self.info.set_property("cmake_target_name", "Curses::Curses")

        def _add_component(name: str, lib_name: str | None = None, requires: list[str] | None = None):
            lib_name = lib_name or name
            self.info.components[name].libs = [lib_name + self._lib_suffix]
            self.info.components[name].set_property("pkg_config_name", lib_name + self._lib_suffix)
            self.info.components[name].includedirs.append(os.path.join("include", "ncurses" + self._suffix))
            self.info.components[name].requires = requires if requires else []

        _add_component("libcurses", lib_name="ncurses")
        _add_component("panel", requires=["libcurses"])
        _add_component("menu", requires=["libcurses"])
        _add_component("form", requires=["libcurses"])

        if self.options.with_tinfo:
            _add_component("tinfo")
            self.info.components["libcurses"].requires += ["tinfo"]

        if self.options.with_ticlib:
            _add_component("ticlib", lib_name="tic", requires=["libcurses"])

        if self.options.with_cxx:
            _add_component("curses++", lib_name="ncurses++", requires=["libcurses"])
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.components["libcurses++"].system_libs.append("util")
            libcxx = stdcpp_library(self)
            if libcxx:
                self.info.components["libcurses++"].system_libs.append(libcxx)

        if is_msvc(self):
            self.info.components["libcurses"].requires += [
                "getopt-for-visual-studio::getopt-for-visual-studio",
                "dirent::dirent",
            ]
            if self.options.with_extended_colors:
                self.info.components["libcurses"].requires += [
                    "naive-tsearch::naive-tsearch",
                ]
        if self.options.with_pcre2:
            self.info.components["form"].requires.append("pcre2::pcre2")

        if not self.options.shared:
            self.info.components["libcurses"].defines = ["NCURSES_STATIC"]
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.components["libcurses"].system_libs = ["dl", "m"]

        module_rel_path = os.path.join(self._module_subfolder, self._module_file)
        self.info.components["libcurses"].builddirs.append(self._module_subfolder)
        self.info.set_property("cmake_build_modules", [module_rel_path])

        terminfo = self.folders.package / "res" / "terminfo"
        self.info.buildenv.define_path("TERMINFO", terminfo.as_posix())
        self.info.runenv.define_path("TERMINFO", terminfo.as_posix())
        self.info.conf.tools.ncurses.lib_suffix = self._lib_suffix

    @property
    def _is_mingw(self):
        return self.settings.os == "Windows" and self.settings.compiler == "gcc"

    @property
    def _suffix(self):
        res = ""
        # https://github.com/mirror/ncurses/blob/v6.4/configure.in#L1393
        if self.options.with_reentrant:
            res += "t"
        # https://github.com/mirror/ncurses/blob/v6.4/configure.in#L959
        if self.options.with_widec:
            res += "w"
        return res

    @property
    def _lib_suffix(self):
        res = self._suffix
        if self.options.shared:
            if self.settings.os == "Windows":
                res += ".dll"
        return res

    @property
    def _module_subfolder(self):
        return os.path.join("lib", "cmake")

    @property
    def _module_file(self):
        return f"recipe-official-{self.name}-targets.cmake"
