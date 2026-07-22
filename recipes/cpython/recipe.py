import base64
import csv
import hashlib
import io
import os
import re
import textwrap
import zipfile
from pathlib import Path
from typing import Any

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os, fix_apple_shared_install_name
from thirdparty.env import VirtualBuildEnv, VirtualRunEnv
from thirdparty.errors import RecipeException
from thirdparty.files import apply_patches, copy, get, load, mkdir, replace_in_file, rm, rmdir, save, unzip
from thirdparty.autotools import Autotools, AutotoolsToolchain, AutotoolsDeps
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.msbuild import MSBuild, MSBuildDeps, MSBuildToolchain
from thirdparty.microsoft import is_msvc, msvc_runtime_flag, msvs_toolset
from thirdparty.scm import GithubRepository, Version
from thirdparty.shell import run
from thirdparty.build.cross_building import cross_building


class _Options(RecipeOptions):
    shared: bool = True
    pic: bool = True
    optimizations: bool = False
    lto: bool = False
    docstrings: bool = True
    pymalloc: bool = True
    with_bsddb: bool = False
    with_bz2: bool = True
    with_curses: bool = True
    with_gdbm: bool = True
    with_lzma: bool = True
    with_sqlite: bool = True
    with_tkinter: bool = True
    env_vars: bool = True


class Recipe(RecipeBase[_Options]):
    name = "cpython"
    version = "3.14.6"
    license = "Python-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "python/cpython")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        if is_msvc(self):
            self.options.lto = False
            self.options.docstrings = False
            self.options.pymalloc = False
            self.options.with_curses = False
            self.options.with_gdbm = False
            # CPython's PCbuild solution builds the _tkinter project only for x64: its ARM64
            # solution configuration has an ActiveCfg but no Build.0 entry, so msbuild reports
            # "target _tkinter does not exist" (MSB4057) when targeting Windows ARM64. Tkinter
            # therefore cannot be built for Windows ARM64; disable it to match CPython's own
            # configuration (the x64 build is unaffected).
            if self.settings.arch == "ARM":
                self.options.with_tkinter = False

        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

        if not self._supports_modules:
            self.options.with_bz2 = False
            self.options.with_sqlite = False
            self.options.with_tkinter = False
            self.options.with_lzma = False

    def requirements(self):
        self.requires("zlib")
        if self._supports_modules:
            self.requires("openssl")
            self.requires("libexpat")
            self.requires("libffi")
            self.requires("mpdecimal")
            self.requires("zstd")
        if self.settings.os != "Windows":
            if not is_apple_os(self):
                self.requires("util-linux")
            self.requires("libxcrypt")
        if self.options.with_bz2:
            self.requires("bzip2")
        if self.options.with_gdbm:
            self.requires("gdbm")
        if self.options.with_sqlite:
            self.requires("sqlite")
        if self.options.with_tkinter:
            self.requires("tk")
            if self.settings.os in ("Linux", "FreeBSD"):
                self.requires("libx11")
                self.requires("libxcb")
                self.requires("libxrender")
                self.requires("libxau")
                self.requires("libxdmcp")
        if self.options.with_curses:
            # Used in a public header
            # https://github.com/python/cpython/blob/v3.10.13/Include/py_curses.h#L34
            self.requires("ncurses")
        if self.options.with_lzma:
            self.requires("xz")
        if not is_msvc(self) and not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")
        # When cross-compiling, the freshly built Python cannot run on the build host. CPython's
        # Unix configure needs a build Python, and the Windows package layout step needs one too.
        if cross_building(self):
            self.requires_tool(self.name)

    def source(self):
        get(
            self,
            url=f"https://github.com/python/cpython/archive/refs/tags/v{self.version}.tar.gz",
            sha256="7f77ccf3613ddadc74dfb8d6f8082581a8835115a25e1307d189f03aa750893e",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        VirtualRunEnv(self).generate(scope="build")

        if is_msvc(self):
            # The msbuild generator only works with Visual Studio
            deps = MSBuildDeps(self)
            deps.generate()
            # The toolchain.props is not injected yet, but it also generates VCVars
            toolchain = MSBuildToolchain(self)
            toolchain.properties["IncludeExternals"] = "true"
            toolchain.generate()
        else:
            self._generate_autotools()

    def build(self):
        self._patch_sources()
        if is_msvc(self):
            self._msvc_build()
        else:
            autotools = Autotools(self)
            autotools.configure()
            autotools.make()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        if is_msvc(self):
            if self.options.shared:
                self._msvc_package_layout()
            else:
                self._msvc_package_copy()
            rm(self, "vcruntime*", self.folders.package / "bin", recursive=True)
        else:
            autotools = Autotools(self)
            if is_apple_os(self):
                # FIXME: See https://github.com/python/cpython/issues/109796, this workaround is mentioned there
                autotools.make(target="sharedinstall", args=["DESTDIR="])
            autotools.install(args=["DESTDIR="])
            rmdir(self, self.folders.package / "lib" / "pkgconfig")
            rmdir(self, self.folders.package / "share")

            # Rewrite shebangs of python scripts
            for filename in os.listdir(self.folders.package / "bin"):
                filepath = self.folders.package / "bin" / filename
                if not os.path.isfile(filepath):
                    continue
                if os.path.islink(filepath):
                    continue
                with open(filepath, "rb") as fn:
                    firstline = fn.readline(1024)
                    if not (firstline.startswith(b"#!") and b"/python" in firstline and b"/bin/sh" not in firstline):
                        continue
                    text = fn.read()
                self.output.info(f"Rewriting shebang of {filename}")
                with open(filepath, "wb") as fn:
                    fn.write(
                        textwrap.dedent(
                            f"""\
                            #!/bin/sh
                            ''':'
                            __file__="$0"
                            while [ -L "$__file__" ]; do
                                __file__="$(dirname "$__file__")/$(readlink "$__file__")"
                            done
                            exec "$(dirname "$__file__")/python{self._version_suffix}" "$0" "$@"
                            '''
                            """).encode())
                    fn.write(text)

            if not os.path.exists(self._cpython_symlink):
                os.symlink(self._cpython_interpreter_name, self._cpython_symlink)
        fix_apple_shared_install_name(self)

        self._write_cmake_findpython_wrapper_file()

    def package_info(self):
        # python component: "Build a C extension for Python"
        if is_msvc(self):
            self.info.components["python"].includedirs = [os.path.join(self._msvc_install_subprefix, "include")]
            libdir = os.path.join(self._msvc_install_subprefix, "libs")
        else:
            self.info.components["python"].includedirs.append(os.path.join("include", "python"))
            libdir = "lib"
        if self.options.shared:
            self.info.components["python"].defines.append("Py_ENABLE_SHARED")
        else:
            self.info.components["python"].defines.append("Py_NO_ENABLE_SHARED")
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.components["python"].system_libs.extend(["dl", "m", "pthread", "util"])
            elif self.settings.os == "Windows":
                self.info.components["python"].system_libs.extend(
                    ["pathcch", "shlwapi", "version", "ws2_32"]
                )
        self.info.components["python"].requires = ["zlib::zlib"]
        if self.settings.os != "Windows":
            self.info.components["python"].requires.append("libxcrypt::libxcrypt")
        self.info.components["python"].set_property(
            "pkg_config_name", "python3"
        )
        self.info.components["python"].set_property(
            "pkg_config_aliases", ["python"]
        )
        self.info.components["python"].libdirs = []

        # embed component: "Embed Python into an application"
        self.info.components["embed"].libs = [self._lib_name]
        self.info.components["embed"].libdirs = [libdir]
        self.info.components["embed"].includedirs = []
        self.info.components["embed"].set_property(
            "pkg_config_name", "python3-embed"
        )
        self.info.components["embed"].set_property(
            "pkg_config_aliases", ["python-embed"]
        )
        self.info.components["embed"].requires = ["python"]

        # Transparent integration with CMake's FindPython(3)
        self.info.set_property("cmake_file_name", "Python3")
        self.info.set_property("cmake_build_modules", [os.path.join(self._cmake_module_path, "use_recipe_python.cmake")])
        self.info.builddirs = [self._cmake_module_path]

        if self._supports_modules:
            # hidden components: the C extensions of python are built as dynamically loaded shared libraries.
            # C extensions or applications with an embedded Python should not need to link to them..
            self.info.components["_hidden"].requires = [
                "openssl::openssl",
                "libexpat::libexpat",
                "mpdecimal::mpdecimal",
                "libffi::libffi",
                "zstd::zstd",
            ]
            if self.settings.os != "Windows":
                if not is_apple_os(self):
                    self.info.components["_hidden"].requires.append("util-linux::util-linux")
                self.info.components["_hidden"].requires.append("libxcrypt::libxcrypt")
            if self.options.with_bz2:
                self.info.components["_hidden"].requires.append("bzip2::bzip2")
            if self.options.with_gdbm:
                self.info.components["_hidden"].requires.append("gdbm::gdbm")
            if self.options.with_sqlite:
                self.info.components["_hidden"].requires.append("sqlite::sqlite")
            if self.options.with_curses:
                self.info.components["_hidden"].requires.append("ncurses::ncurses")
            if self.options.with_lzma:
                self.info.components["_hidden"].requires.append("xz::xz")
            if self.options.with_tkinter:
                self.info.components["_hidden"].requires.append("tk::tk")
            self.info.components["_hidden"].includedirs = []
            self.info.components["_hidden"].libdirs = []
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.components["_hidden"].system_libs.append("nsl")

        if self.options.env_vars:
            bindir = self.folders.package / "bin"
            self.info.runenv.append_path("PATH", bindir)
            self.info.buildenv.append_path("PATH", bindir)

            # TODO remove once Recipe 1.x is no longer supported
            self.output.info(f"Appending PATH environment variable: {bindir}")

            if self.settings.os in ("Linux", "FreeBSD") and self.options.shared:
                # The shared interpreter links libpython<ver>.so.1.0 from lib/ with no rpath, so it
                # cannot run unless that directory is on LD_LIBRARY_PATH. Export it so downstream
                # builds that run the interpreter (e.g. FindPython in pybind11/pyside) work.
                libdir = self.folders.package / "lib"
                self.info.runenv.append_path("LD_LIBRARY_PATH", libdir)
                self.info.buildenv.append_path("LD_LIBRARY_PATH", libdir)

        python = self._cpython_interpreter_path
        self.info.conf.tools.cpython.python = python
        if self.options.env_vars:
            self.info.runenv.append_path("PYTHON", python)
            self.info.buildenv.append_path("PYTHON", python)

            # TODO remove once Recipe 1.x is no longer supported
            self.output.info(f"Appending PYTHON environment variable: {python}")

        if is_msvc(self):
            pythonhome = self.folders.package / "bin"
        else:
            pythonhome = self.folders.package
        self.info.conf.tools.cpython.pythonhome = pythonhome

        pythonhome_required = is_msvc(self) or is_apple_os(self)
        self.info.conf.tools.cpython.module_requires_pythonhome = pythonhome_required

        python_root = self.folders.package
        if self.options.env_vars:
            self.info.runenv.append_path("PYTHON_ROOT", python_root)
            self.info.buildenv.append_path("PYTHON_ROOT", python_root)

        self.info.conf.tools.cpython.python_root = python_root

    @property
    def _supports_modules(self):
        return not is_msvc(self) or self.options.shared

    @property
    def _version_suffix(self):
        v = Version(self.version)
        return f"{v.major}"

    def _generate_autotools(self):
        tc = AutotoolsToolchain(self, prefix=self.folders.package)
        # Not necessary, just cleans up the output
        tc.update_configure_args({"--enable-static": None, "--disable-static": None})

        def yes_no(v: Any) -> str:
            return "yes" if v else "no"

        tc.configure_args += [
            "--enable-shared" if self.options.shared else "--disable-shared",
            f"--with-doc-strings={yes_no(self.options.docstrings)}",
            f"--with-pymalloc={yes_no(self.options.pymalloc)}",
            "--with-system-expat",
            f"--enable-optimizations={yes_no(self.options.optimizations)}",
            f"--with-lto={yes_no(self.options.lto)}",
            f"--with-pydebug={yes_no(self.settings.build_type == "Debug")}",
            "--with-system-libmpdec",
            f"--with-openssl={self.dependencies["openssl"].folders.package}",
        ]
        if cross_building(self):
            build_python = self.dependencies.build[self.name].info.conf.tools.cpython.python
            tc.configure_args.extend([
                f"--with-build-python={build_python}",
                "ac_cv_buggy_getaddrinfo=no",
                "ac_cv_file__dev_ptmx=yes",
                "ac_cv_file__dev_ptc=no",
            ])
        tc.configure_args.append("--disable-test-modules")
        if self.options.with_sqlite:
            tc.configure_args.append(
                f"--enable-loadable-sqlite-extensions={yes_no(not self.dependencies["sqlite"].options.omit_load_extension)}"
            )
        if self._supports_modules and "mpdecimal" in self.dependencies:
            # mpdecimal >= 4.0 renamed CONFIG_64/CONFIG_32 → MPD_CONFIG_64/MPD_CONFIG_32.
            # CPython's _decimal implementation still checks the old names; provide compat defines.
            if Version(str(self.dependencies["mpdecimal"].version)) >= "4.0":
                _arch = str(self.settings.arch)
                if _arch in ("X64", "ARM"):
                    tc.extra_defines.append("CONFIG_64")
                else:
                    tc.extra_defines.append("CONFIG_32")

        if not is_apple_os(self):
            tc.extra_ldflags.append("-Wl,--as-needed")
        else:
            # On macOS, some deps (tcl, tk, gdbm, libxcrypt) use @rpath-based dylib
            # install names. Without explicit -rpath entries, configure test programs
            # abort: "dyld: Library not loaded: @rpath/libtk8.6.dylib, Reason: no
            # LC_RPATH's found". Add -rpath for each of these dep lib directories.
            for _rpath_dep in ("tcl", "tk", "gdbm", "libxcrypt"):
                if _rpath_dep in self.dependencies:
                    _lib_dir = self.dependencies[_rpath_dep].folders.package / "lib"
                    tc.extra_ldflags.append(f"-Wl,-rpath,{_lib_dir}")

        tc.generate()

        deps = AutotoolsDeps(self)
        deps.generate()
        deps = PkgConfigDeps(self)
        deps.generate()

    def _msvc_project_path(self, name: str) -> Path:
        return self.folders.source / "PCbuild" / f"{name}.vcxproj"

    def _regex_replace_in_file(
        self,
        filename: Path,
        pattern: str,
        replacement: str):
        content = load(self, filename)
        content = re.sub(pattern, replacement, content)
        save(self, filename, content)

    def _inject_recipe_props_file(
        self,
        project_basename: str,
        dep_name: str,
        condition: bool = True):
        if condition:
            search = '<Import Project="python.props" />'
            replace_in_file(
                self,
                self._msvc_project_path(project_basename),
                search,
                search + f'<Import Project="{self.folders.generators}/recipe_{dep_name}.props" />')

    def _patch_msvc_projects(self):
        # Produce the interpreter and import library under their final package names. The full
        # runtime intentionally replaces PCbuild's separate stable-ABI python3.dll in this
        # isolated package, so do not build a second project with the same output name.
        replace_in_file(
            self, self.folders.source / "PCbuild" / "python.props",
            '<PyExeName Condition="$(PyExeName) == \'\'">python</PyExeName>',
            '<PyExeName Condition="$(PyExeName) == \'\'">python3</PyExeName>')
        replace_in_file(
            self, self.folders.source / "PCbuild" / "python.props",
            '<PyDllName Condition="$(PyDllName) == \'\'">python$(MajorVersionNumber)$(MinorVersionNumber)$(PyDebugExt)</PyDllName>',
            '<PyDllName Condition="$(PyDllName) == \'\'">python3$(PyDebugExt)</PyDllName>')
        replace_in_file(
            self, self.folders.source / "PC" / "layout" / "support" / "constants.py",
            'PYTHON_DLL_NAME = "python{}{}.dll".format(VER_MAJOR, VER_MINOR)',
            'PYTHON_DLL_NAME = "python3.dll"')
        replace_in_file(
            self, self.folders.source / "PC" / "layout" / "support" / "constants.py",
            'PYTHON_ZIP_NAME = "python{}{}.zip".format(VER_MAJOR, VER_MINOR)',
            'PYTHON_ZIP_NAME = "python.zip"')
        replace_in_file(
            self, self.folders.source / "PC" / "layout" / "support" / "constants.py",
            'PYTHON_PTH_NAME = "python{}{}._pth".format(VER_MAJOR, VER_MINOR)',
            'PYTHON_PTH_NAME = "python3._pth"')
        replace_in_file(
            self, self.folders.source / "PC" / "layout" / "main.py",
            '    source = "python.exe"',
            '    source = "python3.exe"')
        replace_in_file(
            self, self.folders.source / "PC" / "layout" / "main.py",
            '''    alias = [
        "python",
        "python{}".format(VER_MAJOR) if ns.include_alias3 else "",
        "python{}".format(VER_DOT) if ns.include_alias3x else "",
    ]''',
            '''    alias = ["python3"]''')
        replace_in_file(
            self, self._msvc_project_path("_remote_debugging"),
            '<ProjectReference Include="python3dll.vcxproj">',
            '<ProjectReference Include="python3dll.vcxproj" Condition="False">')

        # Don't build vendored bz2
        self._regex_replace_in_file(self._msvc_project_path("_bz2"), r'.*Include=\"\$\(bz2Dir\).*', "")

        if self._supports_modules:
            # Don't import vendored libffi
            replace_in_file(self, self._msvc_project_path("_ctypes"), '<Import Project="libffi.props" />', "")

        # Don't import vendored openssl
        replace_in_file(self, self._msvc_project_path("_hashlib"), '<Import Project="openssl.props" />', "")
        replace_in_file(self, self._msvc_project_path("_ssl"), '<Import Project="openssl.props" />', "")

        # For mpdecimal, we need to remove all headers and all c files *except* the main module file, _decimal.c
        self._regex_replace_in_file(self._msvc_project_path("_decimal"), r'.*Include=\"\.\.\\Modules\\_decimal\\.*\.h.*', "")
        self._regex_replace_in_file(self._msvc_project_path("_decimal"), r'.*Include=\"\.\.\\Modules\\_decimal\\libmpdec\\.*\.c.*', "")
        self._regex_replace_in_file(self._msvc_project_path("_decimal"), r'.*Include=\"\$\(mpdecimalDir\)\\libmpdec\\.*\.(?:c|h).*', "")
        # There is also an assembly file with a complicated build step as part of the mpdecimal build
        replace_in_file(self, self._msvc_project_path("_decimal"), "<CustomBuild", "<!--<CustomBuild")
        replace_in_file(self, self._msvc_project_path("_decimal"), "</CustomBuild>", "</CustomBuild>-->")
        # Remove the vendored mpdecimal include directory. The recipe props add the packaged one.
        replace_in_file(self, self._msvc_project_path("_decimal"), r"$(mpdecimalDir)\libmpdec;", "")

        # Don't include vendored sqlite
        replace_in_file(
            self, self._msvc_project_path("_sqlite3"),
            '<ProjectReference Include="sqlite3.vcxproj">',
            '<ProjectReference Include="sqlite3.vcxproj" Condition="False">')

        # Remove hardcoded reference to lzma library
        replace_in_file(self, self._msvc_project_path("_lzma"), "<AdditionalDependencies>$(OutDir)liblzma$(PyDebugExt).lib;", "<AdditionalDependencies>")
        # Don't include vendored lzma
        replace_in_file(
            self, self._msvc_project_path("_lzma"),
            '<ProjectReference Include="liblzma.vcxproj">',
            '<ProjectReference Include="liblzma.vcxproj" Condition="False">')

        # Don't include vendored expat project
        replace_in_file(
            self, self._msvc_project_path("pyexpat"),
            r"<AdditionalIncludeDirectories>$(PySourcePath)Modules\expat;",
            "<AdditionalIncludeDirectories>")
        # Remove XML_STATIC, this should conditionally be set by the expat library.
        replace_in_file(self, self._msvc_project_path("pyexpat"), "XML_STATIC;", "")
        self._regex_replace_in_file(self._msvc_project_path("pyexpat"), r'.*Include=\"\.\.\\Modules\\expat\\.*" />', "")

        # Don't include vendored expat headers
        replace_in_file(
            self, self._msvc_project_path("_elementtree"),
            r"<AdditionalIncludeDirectories>..\Modules\expat;",
            "<AdditionalIncludeDirectories>")
        # Remove XML_STATIC, this should conditionally be set by the expat library.
        replace_in_file(self, self._msvc_project_path("_elementtree"), "XML_STATIC;", "")
        # Remove vendored expat
        self._regex_replace_in_file(self._msvc_project_path("_elementtree"), r'.*Include=\"\.\.\\Modules\\expat\\.*" />', "")

        # Don't use vendored zlib
        self._regex_replace_in_file(self._msvc_project_path("pythoncore"), r'.*Include=\"\$\(zlibDir\).*', "")
        # CPython 3.14's PCbuild uses vendored zlib-ng in compatibility mode. Link the recipe's
        # zlib instead and remove all zlib-ng source/header entries and its hardcoded import lib.
        self._regex_replace_in_file(self._msvc_project_path("pythoncore"), r'.*Include=\"\$\((?:GeneratedZlibNgDir|zlibNgDir)\).*', "")
        replace_in_file(
            self, self._msvc_project_path("pythoncore"),
            "zlib-ng$(PyDebugExt).lib;", "")
        replace_in_file(
            self, self._msvc_project_path("pythoncore"),
            '<ProjectReference Include="zlib-ng.vcxproj" Condition="$(IncludeExternals)">',
            '<ProjectReference Include="zlib-ng.vcxproj" Condition="False">')

        # Python 3.14 adds compression.zstd. Build the extension against the separately packaged
        # zstd library rather than compiling CPython's vendored zstd sources into the module.
        self._regex_replace_in_file(self._msvc_project_path("_zstd"), r'.*Include=\"\$\(zstdDir\).*', "")
        replace_in_file(
            self, self._msvc_project_path("_zstd"),
            r"$(zstdDir)lib\;$(zstdDir)lib\common;$(zstdDir)lib\compress;$(zstdDir)lib\decompress;$(zstdDir)lib\dictBuilder;",
            "")

        # Don't use vendored tcl/tk include dir
        replace_in_file(self, self._msvc_project_path("_tkinter"), "<AdditionalIncludeDirectories>$(tcltkDir)include;", "<AdditionalIncludeDirectories>")
        # Don't use hardcoded tcl/tk library
        replace_in_file(self, self._msvc_project_path("_tkinter"), "<AdditionalDependencies>$(tcltkLib);", "<AdditionalDependencies>")
        # TODO: Why?
        replace_in_file(
            self, self._msvc_project_path("_tkinter"),
            "<PreprocessorDefinitions Condition=\"'$(BuildForRelease)' != 'true'\">",
            "<PreprocessorDefinitions Condition='False'>")
        # Don't use vendored tcl/tk
        self._regex_replace_in_file(self._msvc_project_path("_tkinter"), r'.*Include=\"\$\(tcltkdir\).*', "")

        # Disable "ValidateUcrtbase" target (TODO: Why?)
        replace_in_file(self, self._msvc_project_path("python"), "$(Configuration) != 'PGInstrument'", "False")

        self._inject_recipe_props_file("_bz2", "bzip2", self.options.with_bz2)
        self._inject_recipe_props_file("_elementtree", "libexpat", self._supports_modules)
        self._inject_recipe_props_file("pyexpat", "libexpat", self._supports_modules)
        self._inject_recipe_props_file("_hashlib", "openssl", self._supports_modules)
        self._inject_recipe_props_file("_ssl", "openssl", self._supports_modules)
        self._inject_recipe_props_file("_sqlite3", "sqlite", self.options.with_sqlite)
        self._inject_recipe_props_file("_tkinter", "tk", self.options.with_tkinter)
        self._inject_recipe_props_file("pythoncore", "zlib")
        self._inject_recipe_props_file("python", "zlib")
        self._inject_recipe_props_file("pythonw", "zlib")
        self._inject_recipe_props_file("_ctypes", "libffi", self._supports_modules)
        self._inject_recipe_props_file("_decimal", "mpdecimal", self._supports_modules)
        self._inject_recipe_props_file("_lzma", "xz", self.options.with_lzma)
        self._inject_recipe_props_file("_zstd", "zstd", self._supports_modules)
        self._inject_recipe_props_file("_bsddb", "libdb", self.options.with_bsddb)

    def _patch_unversioned_artifacts(self):
        """Make the isolated package use stable, major-version-only artifact names."""
        configure_replacements = {
            'LIBRARY=\'libpython$(VERSION)$(ABIFLAGS).a\'':
                'LIBRARY=\'libpython3$(ABIFLAGS).a\'',
            'LDVERSION="$VERSION"': 'LDVERSION="3"',
            'LDVERSION=\'$(VERSION)$(ABIFLAGS)\'': 'LDVERSION=\'3$(ABIFLAGS)\'',
            'INSTSONAME="$LDLIBRARY".$SOVERSION': 'INSTSONAME="$LDLIBRARY"',
            'PY3LIBRARY=libpython3.so': "PY3LIBRARY=''",
            "BINLIBDEST='$(LIBDIR)/python$(VERSION)$(ABI_THREAD)'":
                "BINLIBDEST='$(LIBDIR)/python'",
            "BINLIBDEST='${exec_prefix}/${PLATLIBDIR}/python$(VERSION)$(ABI_THREAD)'":
                "BINLIBDEST='${exec_prefix}/${PLATLIBDIR}/python'",
            "LIBPL='$(prefix)'\"/${PLATLIBDIR}/python${VERSION}${ABI_THREAD}/config-${LDVERSION}\"":
                "LIBPL='$(prefix)'\"/${PLATLIBDIR}/python/config-${LDVERSION}\"",
            "LIBPL='$(prefix)'\"/${PLATLIBDIR}/python${VERSION}${ABI_THREAD}/config-${LDVERSION}-${PLATFORM_TRIPLET}\"":
                "LIBPL='$(prefix)'\"/${PLATLIBDIR}/python/config-${LDVERSION}-${PLATFORM_TRIPLET}\"",
            "'-bundle_loader $(BINDIR)/python$(VERSION)$(EXE)'":
                "'-bundle_loader $(BINDIR)/python3$(EXE)'",
        }
        for filename in ("configure.ac", "configure"):
            path = self.folders.source / filename
            for search, replacement in configure_replacements.items():
                replace_in_file(self, path, search, replacement)

        makefile = self.folders.source / "Makefile.pre.in"
        makefile_replacements = {
            "EXENAME=\t$(BINDIR)/python$(LDVERSION)$(EXE)":
                "EXENAME=\t$(BINDIR)/python3$(EXE)",
            "LIBDEST=\t$(SCRIPTDIR)/python$(VERSION)$(ABI_THREAD)":
                "LIBDEST=\t$(SCRIPTDIR)/python",
            "INCLUDEPY=\t$(INCLUDEDIR)/python$(LDVERSION)":
                "INCLUDEPY=\t$(INCLUDEDIR)/python",
            "CONFINCLUDEPY=\t$(CONFINCLUDEDIR)/python$(LDVERSION)":
                "CONFINCLUDEPY=\t$(CONFINCLUDEDIR)/python",
            "ZIP_STDLIB=python$(VERSION)$(ABI_THREAD).zip": "ZIP_STDLIB=python.zip",
            "libpython3.so:\tlibpython$(LDVERSION).so\n\t$(BLDSHARED) $(NO_AS_NEEDED) -o $@ -Wl,-h$@ $^\n\n": "",
            "$(INSTALL_DATA) Misc/python.pc $(DESTDIR)$(LIBPC)/python-$(LDVERSION).pc":
                "$(INSTALL_DATA) Misc/python.pc $(DESTDIR)$(LIBPC)/python3.pc",
            "$(INSTALL_DATA) Misc/python-embed.pc $(DESTDIR)$(LIBPC)/python-$(LDVERSION)-embed.pc":
                "$(INSTALL_DATA) Misc/python-embed.pc $(DESTDIR)$(LIBPC)/python3-embed.pc",
            "$(INSTALL_SCRIPT) python-config $(DESTDIR)$(BINDIR)/python$(LDVERSION)-config":
                "$(INSTALL_SCRIPT) python-config $(DESTDIR)$(BINDIR)/python3-config",
            "$(INSTALL_SCRIPT) $(SCRIPT_IDLE) $(DESTDIR)$(BINDIR)/idle$(VERSION)":
                "$(INSTALL_SCRIPT) $(SCRIPT_IDLE) $(DESTDIR)$(BINDIR)/idle3",
            "$(INSTALL_SCRIPT) $(SCRIPT_PYDOC) $(DESTDIR)$(BINDIR)/pydoc$(VERSION)":
                "$(INSTALL_SCRIPT) $(SCRIPT_PYDOC) $(DESTDIR)$(BINDIR)/pydoc3",
            "$(DESTDIR)$(MANDIR)/man1/python$(VERSION).1":
                "$(DESTDIR)$(MANDIR)/man1/python3.1",
        }
        for search, replacement in makefile_replacements.items():
            replace_in_file(self, makefile, search, replacement)

        replace_in_file(
            self, makefile,
            '''\t-if test "$(VERSION)" != "$(LDVERSION)"; then \\
\t\tif test -f $(DESTDIR)$(BINDIR)/python$(VERSION)$(EXE) -o -h $(DESTDIR)$(BINDIR)/python$(VERSION)$(EXE); \\
\t\tthen rm -f $(DESTDIR)$(BINDIR)/python$(VERSION)$(EXE); \\
\t\tfi; \\
\t\t(cd $(DESTDIR)$(BINDIR); $(LN) python$(LDVERSION)$(EXE) python$(VERSION)$(EXE)); \\
\tfi
''',
            "")
        self._regex_replace_in_file(
            makefile,
            r"(?s)bininstall: commoninstall altbininstall\n.*?(?=\n# Install the versioned manual page)",
            "bininstall: commoninstall altbininstall\n")
        replace_in_file(
            self, makefile,
            '''maninstall:\taltmaninstall
\t-rm -f $(DESTDIR)$(MANDIR)/man1/python3.1
\t(cd $(DESTDIR)$(MANDIR)/man1; $(LN) -s python$(VERSION).1 python3.1)
''',
            '''maninstall:\taltmaninstall
''')

        getpath = self.folders.source / "Modules" / "getpath.py"
        getpath_replacements = {
            "STDLIB_SUBDIR = f'{platlibdir}/python{VERSION_MAJOR}.{VERSION_MINOR}{ABI_THREAD}'":
                "STDLIB_SUBDIR = f'{platlibdir}/python'",
            "PLATSTDLIB_LANDMARK = f'{platlibdir}/python{VERSION_MAJOR}.{VERSION_MINOR}{ABI_THREAD}/lib-dynload'":
                "PLATSTDLIB_LANDMARK = f'{platlibdir}/python/lib-dynload'",
            "ZIP_LANDMARK = f'{platlibdir}/python{VERSION_MAJOR}{VERSION_MINOR}{ABI_THREAD}.zip'":
                "ZIP_LANDMARK = f'{platlibdir}/python.zip'",
            "    DEFAULT_PROGRAM_NAME = f'python'":
                "    DEFAULT_PROGRAM_NAME = f'python{VERSION_MAJOR}'",
            "    ZIP_LANDMARK = f'python{VERSION_MAJOR}{VERSION_MINOR}{PYDEBUGEXT or \"\"}.zip'":
                "    ZIP_LANDMARK = f'python.zip'",
            'base_executable = f"{dirname(library)}/bin/python{VERSION_MAJOR}.{VERSION_MINOR}"':
                'base_executable = f"{dirname(library)}/bin/python{VERSION_MAJOR}"',
        }
        for search, replacement in getpath_replacements.items():
            replace_in_file(self, getpath, search, replacement)

        sysconfig = self.folders.source / "Lib" / "sysconfig" / "__init__.py"
        posix_scheme = '''        'stdlib': '{installed_base}/{platlibdir}/{implementation_lower}{py_version_short}{abi_thread}',
        'platstdlib': '{platbase}/{platlibdir}/{implementation_lower}{py_version_short}{abi_thread}',
        'purelib': '{base}/lib/{implementation_lower}{py_version_short}{abi_thread}/site-packages',
        'platlib': '{platbase}/{platlibdir}/{implementation_lower}{py_version_short}{abi_thread}/site-packages',
        'include':
            '{installed_base}/include/{implementation_lower}{py_version_short}{abiflags}',
        'platinclude':
            '{installed_platbase}/include/{implementation_lower}{py_version_short}{abiflags}',
'''
        unversioned_posix_scheme = '''        'stdlib': '{installed_base}/{platlibdir}/{implementation_lower}',
        'platstdlib': '{platbase}/{platlibdir}/{implementation_lower}',
        'purelib': '{base}/lib/{implementation_lower}/site-packages',
        'platlib': '{platbase}/{platlibdir}/{implementation_lower}/site-packages',
        'include': '{installed_base}/include/{implementation_lower}',
        'platinclude': '{installed_platbase}/include/{implementation_lower}',
'''
        # The same block is used by the prefix and venv schemes.
        replace_in_file(self, sysconfig, posix_scheme, unversioned_posix_scheme)

        python_config = self.folders.source / "Misc" / "python-config.sh.in"
        python_config_replacements = {
            'LIBS_EMBED="-lpython${VERSION}${ABIFLAGS} @LIBS@ $SYSLIBS"':
                'LIBS_EMBED="-lpython3${ABIFLAGS} @LIBS@ $SYSLIBS"',
            'LIBDEST=${prefix_real}/lib/python${VERSION}': 'LIBDEST=${prefix_real}/lib/python',
            'INCDIR="-I$includedir/python${VERSION}${ABIFLAGS}"': 'INCDIR="-I$includedir/python"',
        }
        for search, replacement in python_config_replacements.items():
            replace_in_file(self, python_config, search, replacement)
        for filename in ("python.pc.in", "python-embed.pc.in"):
            path = self.folders.source / "Misc" / filename
            replace_in_file(
                self, path,
                'Cflags: -I${includedir}/python@VERSION@@ABIFLAGS@',
                'Cflags: -I${includedir}/python')
        replace_in_file(
            self, self.folders.source / "Misc" / "python-embed.pc.in",
            'Libs: -L${libdir} -lpython@VERSION@@ABIFLAGS@',
            'Libs: -L${libdir} -lpython3@ABIFLAGS@')
        replace_in_file(
            self, self.folders.source / "Misc" / "python-config.in",
            "pyver = getvar('VERSION')",
            "pyver = str(getvar('LDVERSION'))")
        self._patch_bundled_pip_entrypoints()

    def _patch_bundled_pip_entrypoints(self):
        """Teach ensurepip's bundled pip wheel to emit pip3 without also emitting pip3.X."""
        wheels = list((self.folders.source / "Lib" / "ensurepip" / "_bundled").glob("pip-*.whl"))
        if len(wheels) != 1:
            raise RecipeException(f"Expected one bundled pip wheel, found {len(wheels)}")

        wheel = wheels[0]
        module_name = "pip/_internal/operations/install/wheel.py"
        search = b'        scripts_to_generate.append(f"pip{get_major_minor_version()} = {pip_script}")\n'
        replacement = b"        # This isolated package installs only the stable pip3 entry point.\n"

        with zipfile.ZipFile(wheel, "r") as source_zip:
            infos = source_zip.infolist()
            contents = {info.filename: source_zip.read(info.filename) for info in infos}
        module = contents.get(module_name)
        if module is None or search not in module:
            raise RecipeException(f"Unable to patch bundled pip entry points in {wheel.name}")
        contents[module_name] = module.replace(search, replacement)

        record_name = next(
            (name for name in contents if name.endswith(".dist-info/RECORD")), None)
        if record_name is None:
            raise RecipeException(f"Unable to find RECORD in {wheel.name}")
        digest = base64.urlsafe_b64encode(
            hashlib.sha256(contents[module_name]).digest()).rstrip(b"=").decode()
        record_input = io.StringIO(contents[record_name].decode(), newline="")
        rows = list(csv.reader(record_input))
        for row in rows:
            if row and row[0] == module_name:
                row[1] = f"sha256={digest}"
                row[2] = str(len(contents[module_name]))
                break
        else:
            raise RecipeException(f"Unable to update RECORD for {module_name}")
        record_output = io.StringIO(newline="")
        csv.writer(record_output, lineterminator="\n").writerows(rows)
        contents[record_name] = record_output.getvalue().encode()

        patched_wheel = wheel.with_suffix(".patched.whl")
        with zipfile.ZipFile(patched_wheel, "w") as destination_zip:
            for info in infos:
                destination_zip.writestr(info, contents[info.filename])
        os.replace(patched_wheel, wheel)

    def _patch_sources(self):
        apply_patches(self)
        self._patch_unversioned_artifacts()
        replace_in_file(
            self, self.folders.source / "configure",
            'OPENSSL_LIBS="-lssl -lcrypto"',
            'OPENSSL_LIBS="-lssl -lcrypto -lz"',
            strict=False)
        if is_msvc(self):
            runtime_library = {
                "MT": "MultiThreaded",
                "MTd": "MultiThreadedDebug",
                "MD": "MultiThreadedDLL",
                "MDd": "MultiThreadedDebugDLL",
            }[msvc_runtime_flag(self)]
            self.output.info("Patching runtime")
            replace_in_file(
                self, self.folders.source / "PCbuild" / "pyproject.props",
                "MultiThreadedDLL", runtime_library, strict=False)
            replace_in_file(
                self, self.folders.source / "PCbuild" / "pyproject.props",
                "MultiThreadedDebugDLL", runtime_library, strict=False)
            replace_in_file(
                self, self.folders.source / "PCbuild" / "pyproject.props",
                "<WholeProgramOptimization>true</WholeProgramOptimization>",
                "<WholeProgramOptimization>false</WholeProgramOptimization>",
                strict=False)

        # Remove vendored packages
        rmdir(self, self.folders.source / "Modules" / "_decimal" / "libmpdec")
        rmdir(self, self.folders.source / "Modules" / "expat")

        # Enable static MSVC cpython
        if not self.options.shared:
            replace_in_file(
                self, self.folders.source / "PCbuild" / "pythoncore.vcxproj",
                "<PreprocessorDefinitions>",
                "<PreprocessorDefinitions>Py_NO_BUILD_SHARED;")
            replace_in_file(
                self, self.folders.source / "PCbuild" / "pythoncore.vcxproj",
                "Py_ENABLE_SHARED",
                "Py_NO_ENABLE_SHARED")
            replace_in_file(
                self, self.folders.source / "PCbuild" / "pythoncore.vcxproj",
                "DynamicLibrary",
                "StaticLibrary")

            replace_in_file(
                self, self.folders.source / "PCbuild" / "python.vcxproj",
                "<Link>",
                "<Link><AdditionalDependencies>shlwapi.lib;ws2_32.lib;pathcch.lib;version.lib;%(AdditionalDependencies)</AdditionalDependencies>")
            replace_in_file(
                self, self.folders.source / "PCbuild" / "python.vcxproj",
                "<PreprocessorDefinitions>",
                "<PreprocessorDefinitions>Py_NO_ENABLE_SHARED;")

            replace_in_file(
                self, self.folders.source / "PCbuild" / "pythonw.vcxproj",
                "<Link>",
                "<Link><AdditionalDependencies>shlwapi.lib;ws2_32.lib;pathcch.lib;version.lib;%(AdditionalDependencies)</AdditionalDependencies>")
            replace_in_file(
                self, self.folders.source / "PCbuild" / "pythonw.vcxproj",
                "<ItemDefinitionGroup>",
                "<ItemDefinitionGroup><ClCompile><PreprocessorDefinitions>Py_NO_ENABLE_SHARED;%(PreprocessorDefinitions)</PreprocessorDefinitions></ClCompile>")

        recipe_toolchain_props = self.folders.generators / MSBuildToolchain.filename
        replace_in_file(
            self, self.folders.source / "PCbuild" / "pythoncore.vcxproj",
            '<Import Project="python.props" />',
            f'<Import Project="{recipe_toolchain_props}" /><Import Project="python.props" />',
        )

        if is_msvc(self):
            self._patch_msvc_projects()

    @property
    def _solution_projects(self):
        if self.options.shared:
            solution_path = self.folders.source / "PCbuild" / "pcbuild.sln"
            projects = set(m.group(1) for m in re.finditer('"([^"]+)\\.vcxproj"', open(solution_path).read()))

            def project_build(name: str) -> bool:
                if os.path.basename(name) in self._msvc_discarded_projects:
                    return False
                if "test" in name:
                    return False
                return True

            projects = list(filter(project_build, projects))
            return projects
        else:
            return ["pythoncore", "python", "pythonw"]

    @property
    def _msvc_discarded_projects(self):
        discarded = {
            "python_uwp",
            "pythonw_uwp",
            "_freeze_importlib",
            "sqlite3",
            "bdist_wininst",
            "liblzma",
            "openssl",
            "python3dll",
            "zlib-ng",
            "xxlimited",
        }
        if not self.options.with_bz2:
            discarded.add("bz2")
        if not self.options.with_sqlite:
            discarded.add("_sqlite3")
        if not self.options.with_tkinter:
            discarded.add("_tkinter")
        if not self.options.with_lzma:
            discarded.add("_lzma")
        return discarded

    @property
    def _msvc_archs(self):
        archs = {
            "X64": "x64",
            "ARM": "ARM64",
        }
        return archs

    def _msvc_build(self):
        msbuild = MSBuild(self)
        msbuild.platform = self._msvc_archs[str(self.settings.arch)]

        projects = self._solution_projects
        self.output.info(f"Building {len(projects)} Visual Studio projects: {projects}")

        sln = self.folders.source / "PCbuild" / "pcbuild.sln"
        # FIXME: Solution files do not pick up the toolset automatically.
        cmd = msbuild.command(sln, targets=projects)
        run(self,f"{cmd} /p:PlatformToolset={msvs_toolset(self)} /p:SkipCopySSLDLL=true")

    @property
    def _msvc_artifacts_path(self):
        build_subdir_lut = {
            "X64": "amd64",
            "ARM": "arm64",
        }
        return self.folders.source / "PCbuild" / build_subdir_lut[str(self.settings.arch)]

    @property
    def _msvc_install_subprefix(self):
        return "bin"

    def _copy_essential_dlls(self):
        if is_msvc(self):
            # Until MSVC builds support cross building, copy dll's of essential (shared) dependencies to python binary location.
            # These dll's are required when running the layout tool using the newly built python executable.
            dest_path = self.folders.build / self._msvc_artifacts_path
            for bin_path in self.dependencies["libffi"].info.bindirs:
                copy(self, "*.dll", src=bin_path, dst=dest_path)
            for bin_path in self.dependencies["libexpat"].info.bindirs:
                copy(self, "*.dll", src=bin_path, dst=dest_path)
            for bin_path in self.dependencies["zlib"].info.bindirs:
                copy(self, "*.dll", src=bin_path, dst=dest_path)

    def _msvc_package_layout(self):
        self._copy_essential_dlls()
        install_prefix = self.folders.package / self._msvc_install_subprefix
        mkdir(self, install_prefix)
        build_path = self._msvc_artifacts_path
        infix = "_d" if self.settings.build_type == "Debug" else ""
        # The built python targets the host arch; when cross-compiling it cannot run on the build
        # machine, so use the host-runnable python provided via the build-context tool_require.
        if cross_building(self):
            host_python_pkg = Path(self.dependencies.build[self.name].folders.package)
            python_built = host_python_pkg / self._msvc_install_subprefix / f"python3{infix}.exe"
        else:
            python_built = build_path / f"python3{infix}.exe"
        layout_args = [
            self.folders.source / "PC" / "layout" / "main.py",
            "-v",
            "-s", self.folders.source,
            "-b", build_path,
            "--copy", install_prefix,
            "-p",
            "--include-pip",
            "--include-venv",
            "--include-dev",
        ]
        if self.options.with_tkinter:
            layout_args.append("--include-tcltk")
        if self.settings.build_type == "Debug":
            layout_args.append("-d")
        python_args = " ".join(f'"{a}"' for a in layout_args)
        run(self,f"{python_built} {python_args}")

        rmdir(self, self.folders.package / "bin" / "tcl")

        rm(self, "LICENSE.txt", install_prefix)
        for file in os.listdir(install_prefix / "libs"):
            if not re.match("python.*", file):
                os.unlink(install_prefix / "libs" / file)

    def _msvc_package_copy(self):
        build_path = self._msvc_artifacts_path
        infix = "_d" if self.settings.build_type == "Debug" else ""
        copy(
            self, "*.exe",
            src=build_path,
            dst=self.folders.package / self._msvc_install_subprefix)
        copy(
            self, "*.dll",
            src=build_path,
            dst=self.folders.package / self._msvc_install_subprefix)
        copy(
            self, "*.pyd",
            src=build_path,
            dst=self.folders.package / self._msvc_install_subprefix / "DLLs")
        copy(
            self, f"python{self._version_suffix}{infix}.lib",
            src=build_path,
            dst=self.folders.package / self._msvc_install_subprefix / "libs")
        copy(
            self, "*",
            src=self.folders.source / "Include",
            dst=self.folders.package / self._msvc_install_subprefix / "include")
        copy(
            self, "pyconfig.h",
            src=self.folders.source / "PC",
            dst=self.folders.package / self._msvc_install_subprefix / "include")
        copy(
            self, "*.py",
            src=self.folders.source / "lib",
            dst=self.folders.package / self._msvc_install_subprefix / "Lib")
        rmdir(self, self.folders.package / self._msvc_install_subprefix / "Lib" / "test")

        packages: dict[str, str] = {}

        def get_name_version(fn: str) -> list[str]:
            return fn.split(".", 2)[:2]

        whldir = self.folders.source / "Lib" / "ensurepip" / "_bundled"
        for fn in filter(lambda n: n.endswith(".whl"), os.listdir(whldir)):
            name, version = get_name_version(fn)
            add = True
            if name in packages:
                _, pversion = get_name_version(packages[name])
                add = Version(version) > Version(pversion)
            if add:
                packages[name] = fn
        for fname in packages.values():
            unzip(
                self, filename=whldir / fname,
                destination=self.folders.package / "bin" / "Lib" / "site-packages")

        interpreter_path = build_path / self._cpython_interpreter_name
        lib_dir_path = (self.folders.package / self._msvc_install_subprefix / "Lib").as_posix()
        run(self,f"{interpreter_path} -c \"import compileall; compileall.compile_dir('{lib_dir_path}')\"")

    @property
    def _exact_lib_name(self):
        prefix = "" if self.settings.os == "Windows" else "lib"
        if self.settings.os == "Windows":
            extension = "lib"
        elif not self.options.shared:
            extension = "a"
        elif is_apple_os(self):
            extension = "dylib"
        else:
            extension = "so"
        return f"{prefix}{self._lib_name}.{extension}"

    @property
    def _cmake_module_path(self):
        if is_msvc(self):
            # On Windows, `lib` is for Python modules, `libs` is for compiled objects.
            # Usually CMake modules are packaged with the latter.
            return os.path.join(self._msvc_install_subprefix, "libs", "cmake")
        else:
            return os.path.join("lib", "cmake")

    def _write_cmake_findpython_wrapper_file(self):
        template = textwrap.dedent(
            """
            if (DEFINED Python3_VERSION_STRING)
                set(_RECIPE_PYTHON_SUFFIX "3")
            else()
                set(_RECIPE_PYTHON_SUFFIX "")
            endif()
            set(Python${_RECIPE_PYTHON_SUFFIX}_EXECUTABLE @PYTHON_EXECUTABLE@)
            set(Python${_RECIPE_PYTHON_SUFFIX}_LIBRARY @PYTHON_LIBRARY@)
    
            # Fails if these are set beforehand
            unset(Python${_RECIPE_PYTHON_SUFFIX}_INCLUDE_DIRS)
            unset(Python${_RECIPE_PYTHON_SUFFIX}_INCLUDE_DIR)
    
            include(${CMAKE_ROOT}/Modules/FindPython${_RECIPE_PYTHON_SUFFIX}.cmake)
    
            # Sanity check: The former comes from FindPython(3), the latter comes from the injected find module
            if(NOT Python${_RECIPE_PYTHON_SUFFIX}_VERSION STREQUAL Python${_RECIPE_PYTHON_SUFFIX}_VERSION_STRING)
                message(FATAL_ERROR "CMake detected wrong cpython version - this is likely a bug with the cpython Recipe package")
            endif()
    
            if (TARGET Python${_RECIPE_PYTHON_SUFFIX}::Module)
                set_target_properties(Python${_RECIPE_PYTHON_SUFFIX}::Module PROPERTIES INTERFACE_LINK_LIBRARIES cpython::python)
            endif()
            if (TARGET Python${_RECIPE_PYTHON_SUFFIX}::SABIModule)
                set_target_properties(Python${_RECIPE_PYTHON_SUFFIX}::SABIModule PROPERTIES INTERFACE_LINK_LIBRARIES cpython::python)
            endif()
            if (TARGET Python${_RECIPE_PYTHON_SUFFIX}::Python)
                set_target_properties(Python${_RECIPE_PYTHON_SUFFIX}::Python PROPERTIES INTERFACE_LINK_LIBRARIES cpython::embed)
            endif()
            """)

        # In order for the package to be relocatable, these variables must be relative to the installed CMake file
        if is_msvc(self):
            python_exe = "${CMAKE_CURRENT_LIST_DIR}/../../" + self._cpython_interpreter_name
            python_library = "${CMAKE_CURRENT_LIST_DIR}/../" + self._exact_lib_name
        else:
            python_exe = "${CMAKE_CURRENT_LIST_DIR}/../../bin/" + self._cpython_interpreter_name
            python_library = "${CMAKE_CURRENT_LIST_DIR}/../" + self._exact_lib_name

        cmake_file = self.folders.package / self._cmake_module_path / "use_recipe_python.cmake"
        content = template.replace("@PYTHON_EXECUTABLE@", python_exe).replace("@PYTHON_LIBRARY@", python_library)
        save(self, cmake_file, content)

    @property
    def _cpython_symlink(self):
        symlink = self.folders.package / "bin" / "python"
        if self.settings.os == "Windows":
            symlink = symlink.parent / f"{symlink.name}.exe"
        return symlink

    @property
    def _cpython_interpreter_name(self):
        python = f"python{self._version_suffix}"
        if is_msvc(self) and self.settings.build_type == "Debug":
            python += "_d"
        if self.settings.os == "Windows":
            python += ".exe"
        return python

    @property
    def _cpython_interpreter_path(self):
        return self.folders.package / "bin" / self._cpython_interpreter_name

    @property
    def _abi_suffix(self):
        res = ""
        if self.settings.build_type == "Debug":
            res += "d"
        return res

    @property
    def _lib_name(self):
        if is_msvc(self):
            if self.settings.build_type == "Debug":
                lib_ext = "_d"
            else:
                lib_ext = ""
        else:
            lib_ext = self._abi_suffix
        return f"python{self._version_suffix}{lib_ext}"
