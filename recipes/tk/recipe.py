import os
import shutil
from pathlib import Path
from typing import Any

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os, fix_apple_shared_install_name
from thirdparty.build import cross_building
from thirdparty.env import VirtualBuildEnv, VirtualRunEnv
from thirdparty.errors import RecipeException
from thirdparty.files import apply_patches, chdir, copy, get, replace_in_file, rmdir
from thirdparty.autotools import Autotools, AutotoolsDeps, AutotoolsToolchain
from thirdparty.nmake import NMakeDeps, NMakeToolchain
from thirdparty.microsoft import is_cl_exe, unix_path
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository
from thirdparty.shell import run


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "tk"
    version = "9.0.4"
    license = "TCL"

    def latest_version(self):
        repo = GithubRepository(self, "tcltk/tk")
        version = repo.latest_tag_matching(
            r"core-(\d+-\d+-\d+)",
            version_transform=lambda value: value.replace("-", "."))
        return Version(version.replace("-", "."))

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_c_standard = "gnu17"

    def requirements(self):
        self.requires("tcl")
        if self.settings.os == "Linux":
            self.requires("fontconfig")
            self.requires("libx11")
            self.requires("libxcb")
            self.requires("libxrender")
            self.requires("libxau")
            self.requires("libxdmcp")
        if not is_cl_exe(self):
            if self.settings.os == "Windows":
                # The non-msvc path runs tk's ./configure shell script (msvc uses makefile.vc via
                # nmake); without win_bash it is handed to cmd.exe ("not recognized as a command").
                self.win_bash = True
                self.requires_tool("msys2")
        # Cross-compiling tk with makefile.vc requires a native tclsh to run during the
        # build (rules.vc: "You must explicitly set TCLSH_NATIVE"). Pull in a build-machine
        # copy of tcl and pass its tclsh as TCLSH_NATIVE (see _build_nmake).
        if cross_building(self) and is_cl_exe(self):
            self.requires_tool("tcl")

    def source(self):
        get(
            self,
            # NB: the GitHub archive omits release-only files (macosx/configure
            # and doc/man.macros), so use the release tarball that ships them.
            url=f"https://prdownloads.sourceforge.net/tcl/tk{self.version}-src.tar.gz",
            sha256="d7a146d2917eb8b5cc95276dbf0e3d03c7464d2b19c1675357857c989301dbb4",
            strip_root=True,
            destination=self.folders.source)
        apply_patches(self)
        # tk's nmake rules.vc sets WARNINGS to -W3/-W4; blank the level so the quiet -w wins (D9025).
        replace_in_file(self, self.folders.source / "win" / "rules.vc", "= -W3", "=", strict=False)
        replace_in_file(self, self.folders.source / "win" / "rules.vc", "= -W4", "=", strict=False)

        if not is_cl_exe(self):
            # Tk 9.0.4's win/Makefile.in ships INSTALL_ROOT empty, unlike tcl's which sets it
            # to $(DESTDIR). With it empty the DESTDIR that autotools.install() passes is
            # ignored and `make install` writes to the real filesystem root (//lib, //share
            # -> "Read-only file system"). Restore the DESTDIR wiring, and fix the one
            # install mkdir that references $(prefix)/lib without the INSTALL_ROOT prefix, so
            # the whole autotools install lands under the package dir.
            makefile_in = self.folders.source / "win" / "Makefile.in"
            replace_in_file(self, makefile_in, "INSTALL_ROOT\t=\n", "INSTALL_ROOT\t= $(DESTDIR)\n")
            replace_in_file(
                self, makefile_in,
                "$($(CYGPATH) $(prefix)/lib)",
                "$($(CYGPATH) $(INSTALL_ROOT)$(prefix)/lib)")

    def generate(self):
        VirtualBuildEnv(self).generate()

        if is_cl_exe(self):
            NMakeToolchain(self).generate()
            NMakeDeps(self).generate()
        else:
            # Inject runenv variables into buildenv
            # This is required because tcl needs to be available when configure tries to
            # run a test executable
            if not cross_building(self):
                VirtualRunEnv(self).generate(scope="build")
                
            def yes_no(v: Any) -> str:
                return "yes" if v else "no"

            tc = AutotoolsToolchain(self)
            # Tk 9 selects static output with --disable-shared and is always
            # threaded; it no longer accepts the generic static/thread switches.
            tc.configure_args = [
                arg for arg in tc.configure_args
                if arg not in ("--enable-static", "--disable-static")]
            tc.configure_args.append(
                f"--enable-symbols={yes_no(self.settings.build_type == "Debug")}"
            )
            tc.configure_args.append(
                f"--enable-64bit={yes_no(self.settings.arch == "X64")}"
            )
            if is_apple_os(self) and cross_building(self) and self.settings.arch == "X64":
                # Tk shares Tcl's native `arch` probe and would otherwise append
                # the ARM build-machine flag to an explicitly x64 cross-build.
                tc.configure_args.append("tcl_cv_cc_arch_arm64=no")
            tc.configure_args.append(f"--enable-aqua={yes_no(is_apple_os(self))}")
            # unix_path: the ./configure runs under msys2 bash on Windows, which eats the
            # backslashes of a raw Windows path (D:\...\lib -> D:...lib) so tclConfig.sh isn't found.
            tc.configure_args.append(
                f"--with-tcl={unix_path(self, str(self.dependencies["tcl"].folders.package / "lib"))}"
            )
            tc.configure_args.append(f"--with-x={yes_no(self.settings.os == "Linux")}")
            tc.make_args.append(
                f"TCL_GENERIC_DIR={unix_path(self, str(self.dependencies["tcl"].folders.package / "include"))}"
            )
            if self.settings.os == "Windows":
                tc.extra_defines.extend(
                    [
                        "UNICODE",
                        "_UNICODE",
                        "_ATL_XP_TARGETING",
                    ]
                )
            if not is_apple_os(self):
                tc.extra_ldflags.append("-Wl,--as-needed")
            tc.generate()

            if self.settings.os == "Linux":
                deps = AutotoolsDeps(self)
                deps.generate()

    def build(self):
        if is_cl_exe(self):
            self._build_nmake()
        else:
            autotools = Autotools(self)
            autotools.configure(build_script_folder=self._get_configure_folder())
            # Tk's configure falls back to a bundled `minizip` when no system `zip` is
            # available, but the Tk release archive ships neither that program nor rules
            # to build it (it has no zlib source of its own). Tcl builds the same native
            # helper for its own zipfs archive (and, in tcl 9, extends it with the -A/-J
            # self-extracting flags Tk's ZIPFS_BUILD=2 rule needs), so reuse it here.
            # Prefer the copy tcl now packages under bin/; fall back to tcl's build dir.
            # Also matters for cross-builds: the helper is compiled with CC_FOR_BUILD and
            # runs on the build machine.
            tcl_pkg = self.dependencies["tcl"].folders.package
            minizip_dirs = [tcl_pkg / "bin", tcl_pkg.parent / "build"]
            for minizip_name in ("minizip", "minizip.exe"):
                for minizip_dir in minizip_dirs:
                    if (minizip_dir / minizip_name).is_file():
                        copy(self, pattern=minizip_name, src=minizip_dir, dst=self.folders.build)
                        break
            if self.settings.os == "Windows":
                # On Windows the helper is minizip.exe, but Tk's Makefile prerequisite is
                # the extension-less `minizip` (EXEEXT_FOR_BUILD comes out empty under
                # clang-cl). Provide both names; msys2 can exec either (PE header sniff).
                minizip_exe = self.folders.build / "minizip.exe"
                minizip_noext = self.folders.build / "minizip"
                if minizip_exe.is_file() and not minizip_noext.is_file():
                    shutil.copyfile(minizip_exe, minizip_noext)
            autotools.make()

    def package(self):
        copy(
            self,
            pattern="license.terms",
            src=self.folders.source,
            dst=self.folders.package / "licenses",
        )
        if is_cl_exe(self):
            self._build_nmake("install")
        else:
            with chdir(self, self.folders.build):
                autotools = Autotools(self)
                autotools.install()
                # DESTDIR is only default initialized for target="install"
                autotools.make(
                    target="install-private-headers",
                    args=[f"DESTDIR={self.folders.package}"],
                )
                rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "man")
        rmdir(self, self.folders.package / "share")

        tkConfigShPath = self.folders.package / "lib" / "tkConfig.sh"
        if os.path.exists(tkConfigShPath):
            # Make tkConfig.sh relocatable. The install paths are baked in via variable
            # substitution in tkConfig.sh.in, so they can only be rewritten to $TK_ROOT
            # here. msvc's makefile.vc bakes in the absolute INSTALLDIR; the autotools
            # build (prefix=/) bakes in /lib, //lib and TK_PREFIX='/'. Handle every form
            # with strict=False so the forms a given build path doesn't emit are skipped.
            # This mirrors tcl's tclConfig.sh handling.
            replace_in_file(self, tkConfigShPath, os.fspath(self.folders.package), "${TK_ROOT}", strict=False)
            replace_in_file(self, tkConfigShPath, self.folders.package.as_posix(), "${TK_ROOT}", strict=False)
            replace_in_file(self, tkConfigShPath, "TK_PREFIX='/'", "TK_PREFIX='${TK_ROOT}'", strict=False)
            replace_in_file(self, tkConfigShPath, "TK_EXEC_PREFIX='/'", "TK_EXEC_PREFIX='${TK_ROOT}'", strict=False)
            for to_replace in ["//", "/"]:
                replace_in_file(self, tkConfigShPath, f"-L{to_replace}lib", "-L${TK_ROOT}/lib", strict=False)
                replace_in_file(self, tkConfigShPath, f"{{{to_replace}lib}}", "{${TK_ROOT}/lib}", strict=False)
                replace_in_file(self, tkConfigShPath, f"='{to_replace}lib", "='${TK_ROOT}/lib", strict=False)
                replace_in_file(self, tkConfigShPath, f"-I{to_replace}include", "-I${TK_ROOT}/include", strict=False)

        fix_apple_shared_install_name(self)

    def package_info(self):
        tk_version = Version(self.version)
        tk_major = tk_version.major
        tk_minor = tk_version.minor
        assert tk_major is not None and tk_minor is not None
        if tk_major >= 9:
            if is_cl_exe(self):
                static_runtime = (
                    "dynamic" not in str(self.settings.compiler_runtime)
                    and "MD" not in str(self.settings.compiler_runtime))
                tk_suffix = "" if self.options.shared else "s" + ("x" if static_runtime else "")
                self.info.libs = [
                    f"tcl9tk{tk_major}{tk_minor}{tk_suffix}",
                    "tkstub",
                ]
            elif self.settings.os == "Windows":
                # The autotools build on Windows (clang) uses the Windows lib-naming
                # convention - no dot between major/minor and no runtime suffix - so the
                # files are tcl9tk90.lib / tkstub.lib, unlike the Unix libtcl9tk9.0.* below.
                self.info.libs = [
                    f"tcl9tk{tk_major}{tk_minor}",
                    "tkstub",
                ]
            else:
                self.info.libs = [
                    f"tcl9tk{tk_major}.{tk_minor}",
                    "tkstub",
                ]
        else:
            lib_infix = f"{tk_major}.{tk_minor}"
            if is_cl_exe(self):
                lib_infix = f"{tk_major}{tk_minor}"
                tk_suffix = "t{}{}{}".format(
                    "" if self.options.shared else "s",
                    "g" if self.settings.build_type == "Debug" else "",
                    "x" if ("dynamic" in str(self.settings.compiler_runtime) or "MD" in str(self.settings.compiler_runtime)) and not self.options.shared else "",
                )
            else:
                tk_suffix = ""
            self.info.libs = [f"tk{lib_infix}{tk_suffix}", f"tkstub{lib_infix}"]
        if self.settings.os == "Windows" and not self.options.shared:
            # Like tcl.h, tk.h decorates its API with __declspec(dllimport) unless STATIC_BUILD
            # is defined; a static tk must publish it so consumers (CPython's _tkinter) link the
            # plain Tk_* symbols. cl.exe consumers usually inherit this from the tcl dependency,
            # but declare it here too so it holds regardless of dep-props aggregation order.
            self.info.defines.append("STATIC_BUILD")
        if self.settings.os == "Mac":
            self.info.frameworks = ["CoreFoundation", "Cocoa", "Carbon", "IOKit"]
        elif self.settings.os == "Windows":
            self.info.system_libs = [
                "netapi32",
                "kernel32",
                "user32",
                "advapi32",
                "userenv",
                "ws2_32",
                "gdi32",
                "comdlg32",
                "imm32",
                "comctl32",
                "shell32",
                "uuid",
                "ole32",
                "oleaut32",
            ]
        elif self.settings.os == "Linux":
            self.info.requires = [
                "tcl::tcl",
                "fontconfig::fontconfig",
                "libx11::x11",
                "libxcb::xcb",
                "libxrender::libxrender",
                "libxau::libxau",
                "libxdmcp::libxdmcp",
            ]

        tk_library = (self.folders.package / "lib" / f"{self.name}{tk_version.major}.{tk_version.minor}").as_posix()
        self.info.runenv.define("TK_LIBRARY", tk_library)

        tk_root = self.folders.package.as_posix()
        self.info.runenv.define("TK_ROOT", tk_root)

    def _get_default_build_system(self):
        if is_apple_os(self):
            return "macosx"
        elif self.settings.os in ("Linux", "FreeBSD"):
            return "unix"
        elif self.settings.os == "Windows":
            return "win"
        else:
            raise ValueError("tk recipe does not recognize os")

    def _get_configure_folder(self, build_system: str | None = None) -> Path:
        if build_system is None:
            build_system = self._get_default_build_system()
        if build_system not in ["win", "unix", "macosx"]:
            raise RecipeException(f"Invalid build system: {build_system}")
        return self.folders.source / build_system

    def _build_nmake(self, target: str = "release"):
        # https://core.tcl.tk/tips/doc/trunk/tip/477.md
        opts: list[str] = []
        if not self.options.shared:
            opts.append("static")
        if self.settings.build_type == "Debug":
            opts.append("symbols")
        if "dynamic" in str(self.settings.compiler_runtime) or "MD" in str(self.settings.compiler_runtime):
            opts.append("msvcrt")
        else:
            opts.append("nomsvcrt")
        if "d" not in str(self.settings.compiler_runtime):
            opts.append("unchecked")
        # https://core.tcl.tk/tk/tktview?name=3d34589aa0
        # https://wiki.tcl-lang.org/page/Building+with+Visual+Studio+2017
        tcl_lib_path: Path = self.dependencies["tcl"].folders.package / "lib"
        tclimplib, tclstublib = None, None
        for lib in os.listdir(tcl_lib_path):
            if not lib.endswith(".lib"):
                continue
            if lib.startswith("tclstub"):
                # Tcl 9.0's nmake build ships the stub library unversioned (tclstub.lib), unlike
                # 8.x's tclstub86.lib, so match the prefix rather than an exact version. Checked
                # before the tcl{ver} import-lib case so tclstub.lib isn't mis-bucketed.
                tclstublib = tcl_lib_path / lib
            elif lib.startswith("tcl{}".format("".join(self.version.split(".")[:2]))):
                tclimplib = tcl_lib_path / lib

        if tclimplib is None or tclstublib is None:
            raise RecipeException("tcl dependency misses tcl and/or tclstub library")

        flags = {
            "INSTALLDIR": self.folders.package,
            "OPTS": ",".join(opts),
            "TCLDIR": self.dependencies["tcl"].folders.package,
            "TCL_LIBRARY": self.dependencies["tcl"].info.runenv.vars(self).get("TCL_LIBRARY"),
            "TCLIMPLIB": tclimplib,
            "TCLSTUBLIB": tclstublib,
        }
        if cross_building(self):
            # Provide a build-machine tclsh so the cross build can run it (rules.vc U1050).
            native_tcl: Path = self.dependencies.build["tcl"].folders.package
            flags["TCLSH_NATIVE"] = next(iter((native_tcl / "bin").glob("tclsh*.exe")))
        config_dir = self._get_configure_folder("win")
        with chdir(self, config_dir):
            run(
                self,
                f"""nmake -nologo -f makefile.vc {" ".join([f'{k}="{v}"' for k, v in flags.items()])} {target}""",
                env="env_build",
            )
