import os
import re
import shutil

import requests

from thirdparty import RecipeBase
from thirdparty.apple import XCRun
from thirdparty.build import cross_building, load_toolchain_args
from thirdparty.env import VirtualBuildEnv
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get, replace_in_file, rm, rmdir
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.microsoft import unix_path
from thirdparty.scm import Version


class Recipe(RecipeBase):
    name = "gcc"
    version = "16.1.0"
    license = "GPL-3.0-only"

    def latest_version(self):
        response = requests.get("https://gcc.gnu.org/releases.html", timeout=30)
        response.raise_for_status()
        versions = [Version(match) for match in re.findall(r"GCC\s+(\d+\.\d+(?:\.\d+)?)", response.text)]
        return max(versions) if versions else None

    def configure(self):
        self.settings.rm_safe("compiler.libcxx")
        self.settings.rm_safe("compiler.cppstd")
        self.settings.rm_safe("compiler.cstd")
        if self.settings_build.os == "Windows":
            self.win_bash = True
            self.conf.define("tools.gnu:disable_flags", ["build_type"])

    def validate(self):
        if self.settings.os not in ("Linux", "Mac", "Windows"):
            raise RecipeInvalidConfiguration("gcc is only supported on Linux, macOS, and Windows hosts")
        if self.settings.os == "Windows" and self.settings.arch != "X64":
            raise RecipeInvalidConfiguration("gcc only supports Windows X64 until the MSYS2 recipe provides native ARM64 MinGW")
        if self._host_triplet() is None:
            raise RecipeInvalidConfiguration(f"gcc does not support {self.settings.os}/{self.settings.arch}")
        if cross_building(self):
            raise RecipeInvalidConfiguration("gcc only supports native builds")

    def requirements(self):
        self.requires("gmp")
        self.requires("isl")
        self.requires("mpc")
        self.requires("mpfr")
        self.requires("zlib")

        if self.settings_build.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")
        else:
            self.requires_tool("flex")

    def source(self):
        get(
            self,
            url=f"https://ftp.gnu.org/gnu/gcc/gcc-{self.version}/gcc-{self.version}.tar.xz",
            sha256="50efb4d94c3397aff3b0d61a5abd748b4dd31d9d3f2ab7be05b171d36a510f79",
            destination=self.folders.source,
            strip_root=True)
        
        replace_in_file(
            self,
            self.folders.source / "gcc" / "config" / "i386" / "t-linux64",
            "m64=../lib64",
            "m64=../lib",
            strict=False)
        replace_in_file(
            self,
            self.folders.source / "libgcc" / "config" / "t-slibgcc-darwin",
            "@shlib_slibdir@",
            os.path.join(self.folders.package, "lib"),
            strict=False)
        if self.settings_build.os == "Windows":
            replace_in_file(
                self,
                self.folders.source / "configure",
                "-L${prefix}/${target}/lib -L${prefix}/mingw/lib -isystem ${prefix}/${target}/include -isystem ${prefix}/mingw/include",
                "-L${prefix}/${target}/lib -L${prefix}/lib -B${prefix}/lib/ -isystem ${prefix}/${target}/include -isystem ${prefix}/include",
                strict=False)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = AutotoolsToolchain(self)

        if host := self._host_triplet():
            tc.configure_args.extend([f"--build={host}", f"--host={host}", f"--target={host}"])

        tc.configure_args.extend([
            "--enable-languages=c,c++",
            "--disable-nls",
            "--disable-multilib",
            "--disable-bootstrap",
            "--disable-lto",
            "--disable-libgomp",
            "--disable-libitm",
            "--disable-libquadmath",
            "--disable-libsanitizer",
            "--disable-libssp",
            "--disable-libstdcxx-pch",
            "--disable-libvtv",
            "--disable-werror",
            f"--with-gmp={unix_path(self, self.dependencies['gmp'].folders.package)}",
            f"--with-mpfr={unix_path(self, self.dependencies['mpfr'].folders.package)}",
            f"--with-mpc={unix_path(self, self.dependencies['mpc'].folders.package)}",
            f"--with-isl={unix_path(self, self.dependencies['isl'].folders.package)}",
            f"--with-zlib={unix_path(self, self.dependencies['zlib'].folders.package)}",
            f"--with-pkgversion=O3DE ThirdParty GCC {self.version}",
            f"--program-suffix=-{self.version}",
            "--with-bugurl=https://github.com/o3de/o3de/issues",
        ])

        if self.settings.os == "Mac":
            xcrun = XCRun(self)
            tc.configure_args.append(f"--with-sysroot={xcrun.sdk_path}")
            tc.configure_args.append("--with-native-system-header-dir=/usr/include")
            tc.make_args.append("BOOT_LDFLAGS=-Wl,-headerpad_max_install_names")
            
        if self.settings_build.os == "Windows":
            tc.configure_args.extend([
                "--prefix=/mingw64",
                "--bindir=/mingw64/bin",
                "--sbindir=/mingw64/bin",
                "--libdir=/mingw64/lib",
                "--libexecdir=/mingw64/lib",
                "--includedir=/mingw64/include",
                "--oldincludedir=/mingw64/include",
                "--with-native-system-header-dir=/mingw64/include",
                "--disable-win32-registry",
                "--enable-threads=posix",
                "--with-gnu-as",
                "--with-gnu-ld",
            ])
            tc.msvc_runtime_flag = None
            tc.msvc_extra_flags = []
            tc.msvc_runtime_link_flags = []
            tc.build_type_link_flags = []

        env = tc.environment()

        if self.settings_build.os == "Windows":
            env.prepend_path("PATH", "/mingw64/bin")
            env.define("CC", "/mingw64/bin/gcc")
            env.define("CXX", "/mingw64/bin/g++")
            env.define("AS", "/mingw64/bin/as")
            env.define("AR", "/mingw64/bin/ar")
            env.define("DLLTOOL", "/mingw64/bin/dlltool")
            env.define("LD", "/mingw64/bin/ld")
            env.define("NM", "/mingw64/bin/nm")
            env.define("OBJDUMP", "/mingw64/bin/objdump")
            env.define("RANLIB", "/mingw64/bin/ranlib")
            env.define("STRIP", "/mingw64/bin/strip")

        tc.generate(env)
        if self.settings_build.os == "Windows":
            self.env_scripts["build"] = [
                script for script in self.env_scripts.get("build", [])
                if not str(script).endswith(("vcvars_env.bat", "vcvars_env.ps1"))
            ]
            for filename in ("env_build.bat", "deactivate_env_build.bat", "vcvars_env.bat", "deactivate_vcvars_env.bat"):
                stale_script = self.folders.generators / filename
                if stale_script.is_file():
                    stale_script.unlink()

    def build(self):
        autotools = Autotools(self)
        if self.settings_build.os == "Windows":
            configure_script = os.path.relpath(
                self.folders.source / "configure",
                self.folders.build).replace("\\", "/")
            configure_args = load_toolchain_args(self.folders.generators).get("configure_args") or ""
            self.run(f'"{configure_script}" {configure_args}', cwd=self.folders.build)
        else:
            autotools.configure()
        autotools.make()

    def package(self):
        autotools = Autotools(self)
        autotools.install(target="install-strip")

        copy(self, "COPYING*", src=self.folders.source, dst=self.folders.package / "licenses", keep_path=False)
        if self.settings.os == "Windows":
            msys2_mingw = self.dependencies["msys2"].folders.package / "bin" / "msys64" / "mingw64"
            package_mingw = self.folders.package / "mingw64"

            shutil.copytree(
                msys2_mingw / "include",
                package_mingw / "include",
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("c++"))
            shutil.copytree(
                msys2_mingw / "x86_64-w64-mingw32",
                package_mingw / "x86_64-w64-mingw32",
                dirs_exist_ok=True)
            for pattern in ("*.a", "*.o"):
                for source_file in (msys2_mingw / "lib").glob(pattern):
                    destination_file = package_mingw / "lib" / source_file.name
                    if not destination_file.exists():
                        shutil.copy2(source_file, destination_file)
            for filename in (
                "ar.exe",
                "as.exe",
                "dlltool.exe",
                "ld.exe",
                "nm.exe",
                "objdump.exe",
                "ranlib.exe",
                "strip.exe",
                "windres.exe",
                "libiconv-2.dll",
                "libintl-8.dll",
                "libwinpthread-1.dll",
                "libzstd.dll",
                "zlib1.dll",
            ):
                shutil.copy2(msys2_mingw / "bin" / filename, package_mingw / "bin" / filename)
            rmdir(self, self.folders.package / "mingw64" / "share")
        else:
            rmdir(self, self.folders.package / "share")
        rm(self, "*.la", self.folders.package, recursive=True)

    def package_info(self):
        self.info.includedirs = []
        self.info.libdirs = []

        if self.settings.os == "Windows":
            bin_dir = self.folders.package / "mingw64" / "bin"
        else:
            bin_dir = self.folders.package / "bin"
        exe = ".exe" if self.settings.os == "Windows" else ""
        cc = bin_dir / f"gcc-{self.version}{exe}"
        cxx = bin_dir / f"g++-{self.version}{exe}"
        ar = bin_dir / f"gcc-ar-{self.version}{exe}"
        nm = bin_dir / f"gcc-nm-{self.version}{exe}"
        ranlib = bin_dir / f"gcc-ranlib-{self.version}{exe}"

        self.info.buildenv.prepend_path("PATH", bin_dir)
        self.info.buildenv.define_path("CC", cc)
        self.info.buildenv.define_path("CXX", cxx)
        self.info.buildenv.define_path("AR", ar)
        self.info.buildenv.define_path("NM", nm)
        self.info.buildenv.define_path("RANLIB", ranlib)

        self.info.conf.define_path("user.gcc:dir", self.folders.package)
        self.info.conf.define(
            "tools.build:compiler_executables",
            {
                "c": cc,
                "cpp": cxx,
            },
        )

    def _host_triplet(self) -> str | None:
        if self.settings.os == "Windows":
            if self.settings.arch == "X64":
                return "x86_64-w64-mingw32"
            return None
        if self.settings.os == "Linux":
            if self.settings.arch == "X64":
                return "x86_64-pc-linux-gnu"
            if self.settings.arch == "ARM":
                return "aarch64-pc-linux-gnu"
        if self.settings.os == "Mac":
            if self.settings.arch == "X64":
                return "x86_64-apple-darwin"
            if self.settings.arch == "ARM":
                return "aarch64-apple-darwin"
        return None
