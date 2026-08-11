import os
import shutil
from pathlib import Path

from thirdparty._internal.model.conf import CompilerExecutable, PathValue

from thirdparty import RecipeBase
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import apply_patches, chdir, copy, get, replace_in_file, rmdir
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.nmake import NMakeToolchain
from thirdparty.microsoft import is_cl_exe
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository
from thirdparty.shell import run


class Recipe(RecipeBase):
    name = "nasm"
    version = "3.02"
    license = "BSD-2-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "netwide-assembler/nasm")
        return Version(repo.latest_release.removeprefix("nasm-"))

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        if self.settings.os == "Windows":
            self.requires_tool("strawberryperl")
            if not is_cl_exe(self):
                self.win_bash = True
                self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://www.nasm.us/pub/nasm/releasebuilds/{self.version}/nasm-{self.version}.tar.xz",
            sha256="87336eba53b4acfe917424ab5d500d2b0054d9f5148d35c2273ccf2cfb712f0d",
            destination=self.folders.source,
            strip_root=True)
        # nasm's autoconf/attribute.h uses the C23 [[x]] attribute form when __GNUC__ is
        # undefined. clang-cl doesn't define __GNUC__ (it mimics MSVC) but does define
        # __has_c_attribute, so it takes the [[x]] path -- yet nasm places those attributes in
        # GNU position (between `inline` and the return type), which clang rejects for [[...]]
        # ("attribute list cannot appear here"). clang fully supports __attribute__, so exclude
        # it from the modern path and let the __attribute__((x)) fallback win. GNU/Linux-clang
        # builds already define __GNUC__ (unaffected); cl.exe builds via msvc.mak, not this
        # header, and define neither macro.
        replace_in_file(
            self, self.folders.source / "autoconf" / "attribute.h",
            "# ifndef __GNUC__",
            "# if !defined(__GNUC__) && !defined(__clang__)",
            strict=False)

    def generate(self):
        VirtualBuildEnv(self).generate()
        if is_cl_exe(self):
            NMakeToolchain(self).generate()
        else:
            tc = AutotoolsToolchain(self)
            if self.settings.arch == "X64":
                tc.extra_cflags.append("-m64")
            if self.settings.os == "Windows":
                # clang-cl defines _MSC_VER but configure still finds <stdnoreturn.h>. nasm's
                # compiler.h then includes it and does `#define no_return noreturn`, and C23's
                # stdnoreturn.h makes `noreturn` a macro ([[noreturn]]) -- which poisons the
                # Windows SDK's DECLSPEC_NORETURN (__declspec(noreturn) -> __declspec([[noreturn]])
                # -> parse error). Report the header absent so nasm takes its _MSC_VER branch
                # (__declspec(noreturn)) and leaves `noreturn` a plain identifier.
                tc.configure_args.append("ac_cv_header_stdnoreturn_h=no")
                # nasm's file.c includes <stringapiset.h> directly (not via <windows.h>), so the
                # SDK's per-arch selector macro -- which <windows.h> derives from _M_AMD64 /
                # _M_ARM64 -- is never defined and <winnt.h> aborts with "No Target Architecture".
                # clang-cl doesn't predefine it, so set it explicitly for the target arch.
                tc.extra_cflags.append("-D_AMD64_" if self.settings.arch == "X64" else "-D_ARM64_")
            tc.generate()

    def build(self):
        apply_patches(self)
        if is_cl_exe(self):
            with chdir(self, self.folders.source):
                # msvc.mak hardcodes /W2 in BUILD_CFLAGS, conflicting with the quiet -w -> D9025.
                replace_in_file(
                    self, os.path.join("Mkfiles", "msvc.mak"),
                    "$(CFLAGS) /W2", "$(CFLAGS)", strict=False)
                run(self,f"nmake /f {os.path.join("Mkfiles", "msvc.mak")}")
        else:
            with chdir(self, self.folders.source):
                autotools = Autotools(self)
                autotools.configure()

                # GCC9 - "pure" attribute on function returning "void"
                replace_in_file(self, "Makefile", "-Werror=attributes", "")
                if self.settings.os == "Windows":
                    # Drop the cosmetic embedded Windows manifest (win/manifest.obj). Building it
                    # needs a resource compiler the hermetic clang toolchain lacks: mingw's
                    # windres wants a gcc preprocessor that isn't packaged, and llvm-rc rejects
                    # nasm's "1 24 <file>" numeric-type .rc syntax. The manifest only sets app
                    # metadata (DPI/long-path awareness) on the executables, not the assembler.
                    replace_in_file(self, "Makefile", "MANIFEST = win/manifest.$(O)", "MANIFEST =", strict=False)
                autotools.make()

    def package(self):
        copy(self, pattern="LICENSE", dst=self.folders.package / "licenses", src=self.folders.source)
        if is_cl_exe(self):
            copy(self, pattern="*.exe", src=self.folders.source, dst=self.folders.package / "bin", keep_path=False)
            with chdir(self, self.folders.package / "bin"):
                shutil.copy2("nasm.exe", "nasmw.exe")
                shutil.copy2("ndisasm.exe", "ndisasmw.exe")
        else:
            with chdir(self, self.folders.source):
                autotools = Autotools(self)
                autotools.install()
            rmdir(self, self.folders.package / "share")
        self._chmod_plus_x(self._nasm)
        self._chmod_plus_x(self._ndisasm)

    def package_info(self):
        self.info.libdirs = []
        self.info.includedirs = []

        compiler_executables: dict[CompilerExecutable, PathValue] = {"asm": self._nasm}
        self.info.conf.tools.build.compiler_executables.update(compiler_executables)
        self.info.buildenv.define_path("NASM", self._nasm)
        self.info.buildenv.define_path("NDISASM", self._ndisasm)
        self.info.buildenv.define_path("AS", self._nasm)
        self.info.buildenv.prepend_path("PATH", self.folders.package / "bin")

    @property
    def _nasm(self):
        suffix = "w.exe" if is_cl_exe(self) else ""
        return self.folders.package / "bin" / f"nasm{suffix}"

    @property
    def _ndisasm(self):
        suffix = "w.exe" if is_cl_exe(self) else ""
        return self.folders.package / "bin" / f"ndisasm{suffix}"

    def _chmod_plus_x(self, filename: Path):
        if os.name == "posix":
            os.chmod(filename, os.stat(filename).st_mode | 0o111)
