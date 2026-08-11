import re
import shutil

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.build import cross_building
from thirdparty.env import VirtualBuildEnv, VirtualRunEnv
from thirdparty.files import get, chdir, copy, apply_patches, mkdir, rename, replace_in_file
from thirdparty.autotools import AutotoolsToolchain, Autotools
from thirdparty.nmake import NMakeDeps, NMakeToolchain
from thirdparty.microsoft import is_clang_cl, is_cl_exe
from thirdparty.shell import run
from thirdparty.scm import Version, WebReleaseIndex


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    cxx: bool = False


class Recipe(RecipeBase[_Options]):
    name = "mpdecimal"
    version = "4.0.1"
    license = "BSD-2-Clause"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://www.bytereef.org/mpdecimal/download.html")
        return Version(index.latest_release(r"mpdecimal-([\d.]+)\.tar\.gz"))

    def configure(self):
        if not self.options.cxx:
            self.settings.compiler_libcxx = None
            self.settings.compiler_cxx_standard = None

    def requirements(self):
        if not is_cl_exe(self) and self.settings_build.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"http://www.bytereef.org/software/mpdecimal/releases/mpdecimal-{self.version}.tar.gz",
            sha256="96d33abb4bb0070c7be0fed4246cd38416188325f820468214471938545b1ac8",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        if is_cl_exe(self):
            deps = NMakeDeps(self)
            deps.generate()

            tc = NMakeToolchain(self)
            if self.options.shared:
                tc.extra_cflags.append("-DMPDECIMAL_DLL")
                if self.options.cxx:
                    tc.extra_cxxflags.append("-DLIBMPDECXX_DLL")
            tc.generate()
        else:
            # inject requires_tool env vars in build scope (not needed if there is no requires_tool)
            VirtualBuildEnv(self).generate()
            # inject requires env vars in build scope
            # it's required in case of native build when there is AutotoolsDeps & at least one dependency which might be shared, because configure tries to run a test executable
            if not cross_building(self):
                VirtualRunEnv(self).generate(scope="build")

            tc = AutotoolsToolchain(self)
            tc.configure_args.append("--enable-cxx" if self.options.cxx else "--disable-cxx")
            tc_env = tc.environment()
            tc_env.append("LDXXFLAGS", ["$LDFLAGS"])
            tc.generate(tc_env)

    def build(self):
        apply_patches(self)
        if is_clang_cl(self):
            # mpdecimal.c's public helpers are defined inline but declared extern in the public
            # header, so consumers (CPython's _decimal) expect out-of-line definitions in the
            # library. clang emits none for them: the ALWAYS_INLINE ones expand to __forceinline
            # (always_inline) under _MSC_VER and the rest use plain `inline` with C99 semantics.
            # cl.exe emits COMDAT copies and GCC uses gnu89 inline, so upstream is fine, but
            # clang-cl leaves the symbols undefined (undefined symbol mpd_isnan / mpd_isnormal).
            # Neutralise inlining for these definitions so each becomes a normal external
            # function (all live only in mpdecimal.c, so no multi-TU duplication; cl.exe and
            # other compilers are untouched).
            mpdecimal_c = self.folders.source / "libmpdec" / "mpdecimal.c"
            replace_in_file(
                self, mpdecimal_c,
                "#if defined(_MSC_VER)\n  #define ALWAYS_INLINE __forceinline",
                "#if defined(__clang__) && defined(_MSC_VER)\n  #define ALWAYS_INLINE\n"
                "#elif defined(_MSC_VER)\n  #define ALWAYS_INLINE __forceinline")
            # The remaining public helpers use the bare `inline` keyword (C99 -> no out-of-line
            # copy under clang). Drop `inline` from each definition so the archive exports them.
            for _ret_type, _func in (
                ("mpd_uint_t", "mpd_msd"),
                ("int", "mpd_exp_digits"),
                ("int", "mpd_isnormal"),
                ("int", "mpd_issubnormal"),
                ("void", "mpd_setdigits"),
            ):
                replace_in_file(
                    self, mpdecimal_c,
                    f"inline {_ret_type}\n{_func}(",
                    f"{_ret_type}\n{_func}(")
        # After patching, the per-library Makefile.vc WARN hardcodes /W4; drop it (the patch
        # rewrites this line, so it must run here rather than in source()) so the quiet -w wins.
        if is_cl_exe(self):
            for _sub in ("libmpdec", "libmpdec++"):
                replace_in_file(
                    self, self.folders.source / _sub / "Makefile.vc",
                    "WARN = /W4 /wd4200", "WARN = /wd4200", strict=False)
        if is_cl_exe(self):
            self._build_msvc()
        else:
            source_dir = self.folders.source
            build_dir = self.folders.build
            autotools = Autotools(self)
            autotools.configure()
            if is_clang_cl(self):
                self._fix_static_obj_output(build_dir)
            # self.output.info(load(self, pathlib.Path("libmpdec", "Makefile")))
            libmpdec, libmpdecpp = self._target_names
            copy(self, "*", source_dir / "libmpdec", build_dir / "libmpdec")
            with chdir(self, "libmpdec"):
                autotools.make(target=libmpdec)
            if self.options.cxx:
                copy(self, "*", source_dir / "libmpdec++", build_dir / "libmpdec++")
                with chdir(self, "libmpdec++"):
                    autotools.make(target=libmpdecpp)

    def package(self):
        pkg_dir = self.folders.package
        copy(self, "LICENSE.txt", src=self.folders.source, dst=pkg_dir / "licenses")
        if is_cl_exe(self):
            source_dir = self.folders.source
            distfolder = self._dist_folder
            # mpdecimal ships pre-configured MSVC headers named mpdecimal{32,64}vc.h (vc is a
            # suffix, not a prefix), which CPython's _decimal windows/ shim includes. The glob
            # must therefore be *vc.h, not vc*.h -- the latter matches nothing, so the header
            # never reached the package and _decimal failed with "cannot open mpdecimal64vc.h".
            copy(self, "*vc.h", src=source_dir / "libmpdec", dst=pkg_dir / "include")
            copy(self, "*.h", src=distfolder, dst=pkg_dir / "include")
            if self.options.cxx:
                copy(self, "*.hh", src=distfolder, dst=pkg_dir / "include")
            copy(self, "*.lib", src=distfolder, dst=pkg_dir / "lib")
            copy(self, "*.dll", src=distfolder, dst=pkg_dir / "bin")
        else:
            build_dir = self.folders.build
            source_dir = self.folders.source
            mpdecdir = build_dir / "libmpdec"
            mpdecppdir = build_dir / "libmpdec++"
            copy(self, "mpdecimal.h", src=mpdecdir, dst=pkg_dir / "include")
            if self.settings.os == "Windows":
                # CPython's _decimal uses a windows/ shim that includes <mpdecimalNNvc.h>
                # (the name mpdecimal's own MSVC build emits) whenever _MSC_VER is defined -
                # which clang-cl does too. The autotools build only produces the configured
                # mpdecimal.h, so also publish it under the vc name the shim expects (64-bit
                # for our X64/ARM targets, 32-bit only for x86).
                bits = "32" if str(self.settings.arch) in ("X86", "x86") else "64"
                shutil.copyfile(
                    pkg_dir / "include" / "mpdecimal.h",
                    pkg_dir / "include" / f"mpdecimal{bits}vc.h")
            if self.options.cxx:
                copy(self, "decimal.hh", src=source_dir / "libmpdec++", dst=pkg_dir / "include")
            builddirs = [mpdecdir]
            if self.options.cxx:
                builddirs.append(mpdecppdir)
            for builddir in builddirs:
                copy(self, "*.a", src=builddir, dst=pkg_dir / "lib")
                copy(self, "*.so", src=builddir, dst=pkg_dir / "lib")
                copy(self, "*.so.*", src=builddir, dst=pkg_dir / "lib")
                copy(self, "*.dylib", src=builddir, dst=pkg_dir / "lib")
                copy(self, "*.dll", src=builddir, dst=pkg_dir / "bin")

    def package_info(self):
        lib_pre_suf = ("", "")
        if is_cl_exe(self):
            if self.options.shared:
                lib_pre_suf = ("lib", f"-{self.version}.dll")
            else:
                lib_pre_suf = ("lib", f"-{self.version}")
        elif self.settings.os == "Windows":
            if self.options.shared:
                lib_pre_suf = ("", ".dll")

        self.info.components["libmpdecimal"].libs = ["{}mpdec{}".format(*lib_pre_suf)]
        if self.options.shared and is_cl_exe(self):
            self.info.components["libmpdecimal"].defines = ["MPDECIMAL_DLL"]

        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["libmpdecimal"].system_libs = ["m"]

        if self.options.cxx:
            self.info.components["libmpdecimal++"].libs = ["{}mpdec++{}".format(*lib_pre_suf)]
            self.info.components["libmpdecimal++"].requires = ["libmpdecimal"]
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.components["libmpdecimal++"].system_libs = ["pthread"]
            if self.options.shared:
                self.info.components["libmpdecimal++"].defines = ["MPDECIMALXX_DLL"]

    @property
    def _dist_folder(self):
        arch_ext = "32" if self.settings.arch == "x86" else "64"
        return self.folders.build / "vcbuild" / f"dist{arch_ext}"

    def _build_msvc(self):
        source_dir = self.folders.source
        build_dir = self.folders.build
        libmpdec_folder = source_dir / "libmpdec"
        libmpdecpp_folder = source_dir / "libmpdec++"

        copy(self, "Makefile.vc", libmpdec_folder, build_dir)
        rename(self, build_dir / "Makefile.vc", libmpdec_folder / "Makefile")

        mpdec_target = "libmpdec-{}.{}".format(self.version, "dll" if self.options.shared else "lib")
        mpdecpp_target = "libmpdec++-{}.{}".format(self.version, "dll" if self.options.shared else "lib")

        builds = [[libmpdec_folder, mpdec_target]]
        if self.options.cxx:
            builds.append([libmpdecpp_folder, mpdecpp_target])

        for build_dir, target in builds:
            with chdir(self, build_dir):
                run(
                    self,
                    """nmake -f Makefile.vc {target} MACHINE={machine} DEBUG={debug} DLL={dll}""".format(
                        target=target,
                        machine=("x64" if self.settings.arch == "X64" else "ansi64"),
                        debug="1" if self.settings.build_type == "Debug" else "0",
                        dll="1" if self.options.shared else "0",
                    ))

        dist_folder = self._dist_folder
        mkdir(self, dist_folder)
        copy(self, "mpdecimal.h", libmpdec_folder, dist_folder)
        if self.options.shared:
            copy(self, f"libmpdec-{self.version}.dll", libmpdec_folder, dist_folder)
            copy(self, f"libmpdec-{self.version}.dll.lib", libmpdec_folder, dist_folder)
        else:
            copy(self, f"libmpdec-{self.version}.lib", libmpdec_folder, dist_folder)
        if self.options.cxx:
            if self.options.shared:
                copy(self, f"libmpdec++-{self.version}.dll", libmpdecpp_folder, dist_folder)
                copy(self, f"libmpdec++-{self.version}.dll.lib", libmpdecpp_folder, dist_folder)
            else:
                copy(self, f"libmpdec++-{self.version}.lib", libmpdecpp_folder, dist_folder)
            copy(self, "decimal.hh", libmpdecpp_folder, dist_folder)

    def _fix_static_obj_output(self, base_dir):
        # The static-lib rules compile with `-c foo.c` and no -o, relying on the GNU cc default
        # of foo.o; clang-cl writes foo.obj instead, so the archive step can't find foo.o.
        # Append an explicit -o (the shared-lib rules already do this). The Makefiles are
        # generated out-of-source, so they live under the build dir.
        for sub in ("libmpdec", "libmpdec++"):
            makefile = base_dir / sub / "Makefile"
            if makefile.is_file():
                text = makefile.read_text(encoding="utf-8")
                text = re.sub(r"(-c ([A-Za-z0-9_]+)\.(cc|c))$", r"\1 -o \2.o", text, flags=re.M)
                makefile.write_text(text, encoding="utf-8")

    @property
    def _shared_suffix(self):
        if is_apple_os(self):
            return ".dylib"
        return {
            "Windows": ".dll",
        }.get(str(self.settings.os), ".so")

    @property
    def _target_names(self):
        libsuffix = self._shared_suffix if self.options.shared else ".a"
        versionsuffix = f".{self.version}" if self.options.shared else ""
        suffix = (
            f"{versionsuffix}{libsuffix}"
            if is_apple_os(self) or self.settings.os == "Windows"
            else f"{libsuffix}{versionsuffix}"
        )
        return f"libmpdec{suffix}", f"libmpdec++{suffix}"
