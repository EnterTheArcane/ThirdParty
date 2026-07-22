import os
import shutil
from pathlib import Path

from thirdparty._internal.model.conf import CompilerExecutable, PathValue

from thirdparty import RecipeBase
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import apply_patches, chdir, copy, get, replace_in_file, rmdir
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.nmake import NMakeToolchain
from thirdparty.microsoft import is_msvc
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
            if not is_msvc(self):
                self.win_bash = True
                self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://www.nasm.us/pub/nasm/releasebuilds/{self.version}/nasm-{self.version}.tar.xz",
            sha256="87336eba53b4acfe917424ab5d500d2b0054d9f5148d35c2273ccf2cfb712f0d",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        if is_msvc(self):
            NMakeToolchain(self).generate()
        else:
            tc = AutotoolsToolchain(self)
            if self.settings.arch == "X64":
                tc.extra_cflags.append("-m64")
            tc.generate()

    def build(self):
        apply_patches(self)
        if is_msvc(self):
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
                autotools.make()

    def package(self):
        copy(self, pattern="LICENSE", dst=self.folders.package / "licenses", src=self.folders.source)
        if is_msvc(self):
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
        suffix = "w.exe" if is_msvc(self) else ""
        return self.folders.package / "bin" / f"nasm{suffix}"

    @property
    def _ndisasm(self):
        suffix = "w.exe" if is_msvc(self) else ""
        return self.folders.package / "bin" / f"ndisasm{suffix}"

    def _chmod_plus_x(self, filename: Path):
        if os.name == "posix":
            os.chmod(filename, os.stat(filename).st_mode | 0o111)
