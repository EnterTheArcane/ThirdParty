from thirdparty import RecipeBase
from thirdparty.build import cross_building
from thirdparty.env import VirtualBuildEnv
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.microsoft import unix_path
from thirdparty.scm import GnuFtp, Version


class Recipe(RecipeBase):
    name = "mpc"
    version = "1.4.1"
    license = "LGPL-3.0-or-later"

    def latest_version(self):
        return Version(GnuFtp(self, "mpc").latest_release)

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_c_standard = None
        if self.settings_build.os == "Windows":
            self.win_bash = True
            self.conf.tools.gnu.disable_flags = ["build_type"]

    def validate(self):
        if self.settings.os not in ("Linux", "Mac", "Windows"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on desktop host platforms")
        if self.settings.os == "Windows" and self.settings.arch != "X64":
            raise RecipeInvalidConfiguration(f"{self.name} only supports Windows X64 for the MSYS2/MinGW bootstrap")
        if cross_building(self):
            raise RecipeInvalidConfiguration(f"{self.name} only supports native builds")

    def requirements(self):
        self.requires("gmp")
        self.requires("mpfr")
        if self.settings_build.os == "Windows":
            self.win_bash = True
            self.requires_tool("msys2")

    def source(self):
        get(
            self,
            url=f"https://ftp.gnu.org/gnu/mpc/mpc-{self.version}.tar.xz",
            sha256="91204cd32f164bd3b7c992d4a6a8ce6519511aadab30f78b6982d0bf8d73e931",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = AutotoolsToolchain(self)
        tc.configure_args.extend([
            "--disable-shared",
            "--enable-static",
            f"--with-gmp={unix_path(self, self.dependencies['gmp'].folders.package)}",
            f"--with-mpfr={unix_path(self, self.dependencies['mpfr'].folders.package)}",
        ])

        if host := self._host_triplet():
            tc.configure_args.extend([f"--build={host}", f"--host={host}"])

        if self.settings_build.os == "Windows":
            tc.msvc_runtime_flag = None
            tc.msvc_extra_flags = []
            tc.msvc_runtime_link_flags = []
            tc.build_type_link_flags = []

        env = tc.environment()

        if self.settings_build.os == "Windows":
            env.prepend_path("PATH", "/mingw64/bin")
            env.append("CFLAGS", "-std=gnu17")
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
        autotools.configure()
        autotools.make()

    def package(self):
        copy(self, "COPYING.LESSER", src=self.folders.source, dst=self.folders.package / "licenses")
        autotools = Autotools(self)
        autotools.install()
        rmdir(self, self.folders.package / "share")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rm(self, "*.la", self.folders.package / "lib")

    def package_info(self):
        self.info.libs = ["mpc"]
        if self.settings.os != "Windows":
            self.info.system_libs = ["m"]

    def _host_triplet(self) -> str | None:
        if self.settings.os != "Windows":
            return None
        if self.settings.arch == "X64":
            return "x86_64-w64-mingw32"
        return None
