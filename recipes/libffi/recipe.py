import os
import shutil

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, mkdir, rm, rmdir
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.microsoft import check_min_vs, is_msvc, is_msvc_static_runtime, msvc_runtime_flag, unix_path
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libffi"
    version = "3.7.1"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "libffi/libffi")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        if self.settings_build.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")
        if self.settings_build.os == "Windows" and self.settings.compiler_runtime:
            self.requires_tool("automake")

    def source(self):
        get(
            self,
            url=f"https://github.com/libffi/libffi/releases/download/v{self.version}/libffi-{self.version}.tar.gz",
            sha256="d5e9a6638ddbd2513ddb54518eb67e4bbe6fa707bcc01c10f6212f0a088d819d",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        def yes_no(v: bool) -> str:
            return "yes" if v else "no"

        tc = AutotoolsToolchain(self)
        tc.configure_args.extend(
            [
                f"--enable-debug={yes_no(self.settings.build_type == "Debug")}",
                "--enable-builddir=no",
                "--enable-docs=no",
                "--enable-shared" if self.options.shared else "--disable-shared",
                "--disable-static" if self.options.shared else "--enable-static",
            ])

        if self.settings_build.compiler == "apple-clang":
            tc.configure_args.append("--disable-multi-os-directory")

        if self.options.shared:
            tc.extra_defines.append("FFI_BUILDING_DLL")
        if not self.options.shared:
            tc.extra_defines.append("FFI_STATIC_BUILD")

        env = tc.environment()
        if self.settings_build.os == "Windows" and self.settings.compiler_runtime:

            if is_msvc(self) and check_min_vs(self, "180", raise_invalid=False):
                # upstream issue 6514
                tc.extra_cflags.append("-FS")

            if is_msvc_static_runtime(self):
                tc.extra_defines.append("USE_STATIC_RTL")
            if "d" in msvc_runtime_flag(self):
                tc.extra_defines.append("USE_DEBUG_RTL")

            architecture_flag = ""
            if is_msvc(self):
                if self.settings.arch == "X64":
                    architecture_flag = "-m64"
                elif self.settings.arch == "ARM":
                    architecture_flag = "-marm64"
            elif self.settings.compiler == "clang":
                architecture_flag = "-clang-cl"

            compile_wrapper = unix_path(self, self.folders.source / "msvcc.sh")
            if architecture_flag:
                compile_wrapper = f"{compile_wrapper} {architecture_flag}"

            ar_wrapper = unix_path(self, self.dependencies.build["automake"].info.conf.tools.automake.lib_wrapper)
            env.define("CC", f"{compile_wrapper}")
            env.define("CXX", f"{compile_wrapper}")
            env.define("LD", "link -nologo")
            env.define("AR", f"{ar_wrapper} \"lib -nologo\"")
            env.define("NM", "dumpbin -symbols")
            env.define("OBJDUMP", ":")
            env.define("RANLIB", ":")
            env.define("STRIP", ":")
            env.define("CXXCPP", "cl -nologo -EP")
            env.define("CPP", "cl -nologo -EP")
            env.define("LIBTOOL", unix_path(self, self.folders.source / "ltmain.sh") or "")
            env.define("INSTALL", unix_path(self, self.folders.source / "install-sh") or "")
        tc.generate(env=env)

    def build(self):
        autotools = Autotools(self)
        autotools.configure()
        autotools.make()

    def package(self):
        autotools = Autotools(self)
        autotools.install(args=[f"DESTDIR={unix_path(self, self.folders.package)}"])  # Need to specify the `DESTDIR` as a Unix path, aware of the subsystem
        fix_apple_shared_install_name(self)
        mkdir(self, self.folders.package / "bin")
        for dll in (self.folders.package / "lib").glob("*.dll"):
            shutil.move(dll, self.folders.package / "bin")
        if is_msvc(self) and self.options.shared:
            for lib_path in (self.folders.package / "lib").glob("*.dll.lib"):
                libname = os.path.basename(lib_path)[:-len(".dll.lib")]
                dst = self.folders.package / "lib" / f"{libname}.lib"
                if os.path.isfile(dst):
                    os.remove(dst)
                shutil.move(lib_path, dst)
        elif is_msvc(self) and not self.options.shared:
            for a_path in (self.folders.package / "lib").glob("*.a"):
                libname = os.path.basename(a_path)[:-2]  # strip .a
                dst = self.folders.package / "lib" / f"{libname}.lib"
                if os.path.isfile(dst):
                    os.remove(dst)
                shutil.move(a_path, dst)
        copy(self, "LICENSE", self.folders.source, self.folders.package / "licenses")
        rm(self, "*.la", self.folders.package / "lib", recursive=True)
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.libs = ["{}ffi".format("lib" if is_msvc(self) else "")]
        self.info.set_property("pkg_config_name", "libffi")
        if not self.options.shared:
            static_define = "FFI_STATIC_BUILD"
            self.info.defines = [static_define]
