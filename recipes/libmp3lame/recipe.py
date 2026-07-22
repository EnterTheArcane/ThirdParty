import os
import shutil

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import apply_patches, chdir, copy, get, rename, replace_in_file, rm, rmdir
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.nmake import NMakeToolchain
from thirdparty.microsoft import is_msvc
from thirdparty.shell import run
from thirdparty.scm import SourceForgeProject, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libmp3lame"
    version = "4.0"
    license = "LGPL-2.0"

    def latest_version(self):
        project = SourceForgeProject(self, "lame")
        return Version(project.latest_release(r"lame-([\d.]+)\.tar\.gz"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        if not is_msvc(self) and not self._is_clang_cl:
            self.requires_tool("gnu-config")
            # LAME 4.0's configure script requires pkg-config even when the
            # optional frontend is disabled.
            self.requires_tool("pkgconf")
            if self.settings.os == "Windows":
                self.win_bash = True
                self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://downloads.sourceforge.net/project/lame/lame/{self.version}/lame-{self.version}.tar.gz",
            sha256="3df5124d5ad3a98312ffd7ba6a9b36230e4f8a3e66d3ce0f425e336c32d216eb",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        if is_msvc(self) or self._is_clang_cl:
            NMakeToolchain(self).generate()
        else:
            VirtualBuildEnv(self).generate()
            tc = AutotoolsToolchain(self)
            tc.configure_args.append("--disable-frontend")
            tc.configure_args.append("--disable-decoder")
            if self.settings.compiler == "clang" and self.settings.arch in ["X64"]:
                tc.extra_cxxflags.extend(["-mmmx", "-msse"])
            tc.generate()

    def build(self):
        if is_msvc(self) or self._is_clang_cl:
            self._build_vs()
        else:
            self._build_autotools()

    def package(self):
        copy(self, pattern="LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        if is_msvc(self) or self._is_clang_cl:
            copy(self, pattern="*.h", src=self.folders.source / "include", dst=self.folders.package / "include" / "lame")
            name = "libmp3lame.lib" if self.options.shared else "libmp3lame-static.lib"
            copy(self, name, src=self.folders.source / "output", dst=self.folders.package / "lib")
            if self.options.shared:
                copy(self, pattern="*.dll", src=self.folders.source / "output", dst=self.folders.package / "bin")
            rename(
                self, self.folders.package / "lib" / name,
                self.folders.package / "lib" / "mp3lame.lib")
        else:
            autotools = Autotools(self)
            autotools.install()
            rmdir(self, self.folders.package / "share")
            rm(self, "*.la", self.folders.package / "lib")
            fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.libs = ["mp3lame"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs = ["m"]

    @property
    def _is_clang_cl(self):
        return str(self.settings.compiler) in ["clang"] and str(self.settings.os) in ["Windows"]

    def _build_vs(self):
        with chdir(self, self.folders.source):
            shutil.copy2("configMS.h", "config.h")
            # Honor vc runtime
            replace_in_file(self, "Makefile.MSVC", "CC_OPTS = $(CC_OPTS) /MT", "", strict=False)
            # Do not hardcode LTO
            replace_in_file(self, "Makefile.MSVC", " /GL", "", strict=False)
            replace_in_file(self, "Makefile.MSVC", " /LTCG", "", strict=False)
            replace_in_file(self, "Makefile.MSVC", "ADDL_OBJ = bufferoverflowU.lib", "", strict=False)
            command = "nmake -f Makefile.MSVC comp=msvc"
            if self._is_clang_cl:
                compilers_from_conf = self.conf.tools.build.compiler_executables
                buildenv_vars = VirtualBuildEnv(self).vars()
                cl = compilers_from_conf.get("c", buildenv_vars.get("CC", "clang-cl"))
                link = buildenv_vars.get("LD", "lld-link")
                replace_in_file(self, "Makefile.MSVC", "CC = cl", f"CC = {cl}", strict=False)
                replace_in_file(self, "Makefile.MSVC", "LN = link", f"LN = {link}", strict=False)
                # what is /GAy? MSDN doesn't know it
                # clang-cl: error: no such file or directory: '/GAy'
                # https://docs.microsoft.com/en-us/cpp/build/reference/ga-optimize-for-windows-application?view=msvc-170
                replace_in_file(self, "Makefile.MSVC", "/GAy", "/GA", strict=False)
            if self.settings.arch == "X64":
                replace_in_file(self, "Makefile.MSVC", "MACHINE = /machine:I386", "MACHINE =/machine:X64", strict=False)
                command += " MSVCVER=Win64 asm=yes"
            elif self.settings.arch == "ARM":
                replace_in_file(self, "Makefile.MSVC", "MACHINE = /machine:I386", "MACHINE =/machine:ARM64", strict=False)
                command += " MSVCVER=Win64"
            else:
                command += " asm=yes"
            command += " libmp3lame.dll" if self.options.shared else " libmp3lame-static.lib"
            run(self,command)

    def _build_autotools(self):
        for gnu_config in [
            self.conf.tools.gnu_config.config_guess,
            self.conf.tools.gnu_config.config_sub,
        ]:
            if gnu_config:
                copy(self, os.path.basename(gnu_config), src=os.path.dirname(gnu_config), dst=self.folders.source)
        autotools = Autotools(self)
        autotools.configure()
        autotools.make()
