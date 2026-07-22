from thirdparty import RecipeBase, RecipeOptions
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.build import cross_building
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import Version, WebReleaseIndex


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libxext"
    version = "1.3.7"
    license = "MIT"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://www.x.org/releases/individual/lib/")
        return Version(index.latest_release(r"libXext-([\d.]+)\.tar\.xz"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        from thirdparty.errors import RecipeInvalidConfiguration
        if self.settings.os not in ("Linux", "FreeBSD", "Android"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux-like platforms")

    def requirements(self):
        self.requires("xorg-proto")
        self.requires("libx11")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://www.x.org/releases/individual/lib/libXext-{self.version}.tar.xz",
            sha256="6c643c7035cdacf67afd68f25d01b90ef889d546c9fcd7c0adf7c2cf91e3a32d",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        PkgConfigDeps(self).generate()
        tc = AutotoolsToolchain(self)
        if cross_building(self):
            tc.configure_args.append("xorg_cv_malloc0_returns_null=no")
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
        self.info.set_property("pkg_config_name", "xext")
        self.info.libs = ["Xext"]
        self.info.requires = ["libx11::x11", "xorg-proto::xextproto"]
