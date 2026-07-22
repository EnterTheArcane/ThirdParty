from thirdparty import RecipeBase
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.scm import Version, WebReleaseIndex


class Recipe(RecipeBase):
    name = "xtrans"
    version = "1.6.0"
    license = "MIT"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://www.x.org/releases/individual/lib/")
        return Version(index.latest_release(r"xtrans-([\d.]+)\.tar\.xz"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        from thirdparty.errors import RecipeInvalidConfiguration
        if self.settings.os not in ("Linux", "FreeBSD", "Android"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux-like platforms")

    def requirements(self):
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://www.x.org/releases/individual/lib/xtrans-{self.version}.tar.xz",
            sha256="faafea166bf2451a173d9d593352940ec6404145c5d1da5c213423ce4d359e92",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        tc = AutotoolsToolchain(self)
        tc.generate()

    def build(self):
        autotools = Autotools(self)
        autotools.configure()
        autotools.make()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        autotools = Autotools(self)
        autotools.install()
        rm(self, "*.la", self.folders.package / "lib")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        # Header/macro-only: libX11 etc. #include the Xtrans sources via pkg-config `xtrans`.
        self.info.bindirs = []
        self.info.libdirs = []
        self.info.includedirs = ["include"]
        self.info.set_property("pkg_config_name", "xtrans")
