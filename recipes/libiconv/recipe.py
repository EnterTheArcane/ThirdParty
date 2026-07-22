import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name
from thirdparty.build import cross_building
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import (
    apply_patches,
    copy,
    get,
    rename,
    rm,
    rmdir,
    replace_in_file,
)
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.scm import GnuFtp
from thirdparty.microsoft import is_msvc, unix_path
from thirdparty.scm import Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libiconv"
    version = "1.19"
    license = "LGPL-2.1-or-later"

    def latest_version(self):
        repo = GnuFtp(self, "libiconv")
        return Version(repo.latest_release)

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        if self.settings_build.os == "Windows":
            self.requires_tool("msys2")
            self.win_bash = True

    def source(self):
        get(
            self,
            url=f"https://ftpmirror.gnu.org/gnu/libiconv/libiconv-{self.version}.tar.gz",
            sha256="88dd96a8c0464eca144fc791ae60cd31cd8ee78321e67397e25fc095c4a19aa6",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = AutotoolsToolchain(self)
        if cross_building(self) and is_msvc(self):
            triplet_arch_windows = {"X64": "x86_64", "ARM": "aarch64"}
            # ICU doesn't like GNU triplet of recipe for msvc (see upstream issue 12546)
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
        env = tc.environment()
        if is_msvc(self) or self._is_clang_cl:
            cc, lib, link = self._msvc_tools
            if cc.endswith("cl"):
                cc = f"{cc} -nologo"
            build_aux_path = self.folders.source / "build-aux"
            lt_compile = unix_path(self, build_aux_path / "compile")
            lt_ar = unix_path(self, build_aux_path / "ar-lib")
            env.define("CC", f"{lt_compile} {cc}")
            env.define("CXX", f"{lt_compile} {cc}")
            env.define("LD", link)
            env.define("STRIP", ":")
            env.define("AR", f"{lt_ar} {lib}")
            env.define("RANLIB", ":")
            env.define("NM", "dumpbin -symbols")
            env.define("win32_target", "_WIN32_WINNT_VISTA")
        tc.generate(env)

    def build(self):
        apply_patches(self)
        self._apply_resource_patch()
        autotools = Autotools(self)
        autotools.configure()
        if self.settings.os == "Windows" and self.settings.arch == "ARM":
            # GNU windres cannot emit ARM64 COFF objects (its only PE targets are
            # pe-x86-64 / pe-i386), so the compiled version resource would be an x64
            # object and fail to link into the ARM64 DLL/exe (LNK1112). Drop the
            # purely-cosmetic version resource from the link on ARM64.
            for makefile, obj in (("lib", "libiconv.res.lo"), ("src", "iconv.res")):
                replace_in_file(
                    self, self.folders.build / makefile / "Makefile",
                    f"OBJECTS_RES_yes = {obj}", "OBJECTS_RES_yes =", strict=False)
        autotools.make()

    def package(self):
        copy(self, "COPYING.LIB", self.folders.source, self.folders.package / "licenses")
        autotools = Autotools(self)
        autotools.install()
        rm(self, "*.la", self.folders.package / "lib")
        rmdir(self, self.folders.package / "share")
        fix_apple_shared_install_name(self)
        if (is_msvc(self) or self._is_clang_cl) and self.options.shared:
            for import_lib in ["iconv", "charset"]:
                dst = self.folders.package / "lib" / f"{import_lib}.lib"
                if os.path.isfile(dst):
                    os.remove(dst)
                rename(
                    self, self.folders.package / "lib" / f"{import_lib}.dll.lib",
                    self.folders.package / "lib" / f"{import_lib}.lib")

    def package_info(self):
        self.info.set_property("cmake_file_name", "Iconv")
        self.info.set_property("cmake_target_name", "Iconv::Iconv")
        self.info.libs = ["iconv", "charset"]

    @property
    def _is_clang_cl(self):
        return self.settings.compiler == "clang" and self.settings.os == "Windows" and \
            self.settings.compiler_runtime

    @property
    def _msvc_tools(self) -> tuple[str, str, str]:
        compilers = self.conf.tools.build.compiler_executables
        compiler = compilers.get("c") or compilers.get("cpp")
        return (os.fspath(compiler) if compiler else "clang-cl", "llvm-lib", "lld-link") if self._is_clang_cl else ("cl", "lib", "link")

    def _apply_resource_patch(self):
        if self.settings.arch == "x86":
            windres_options_path = self.folders.source / "windows" / "windres-options"
            self.output.info(f"Applying {self.settings.arch} resource patch: {windres_options_path}")
            replace_in_file(self, windres_options_path, "#   PACKAGE_VERSION_SUBMINOR", '#   PACKAGE_VERSION_SUBMINOR\necho "--target=pe-i386"', strict=True)
