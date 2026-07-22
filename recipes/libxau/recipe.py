from thirdparty import RecipeBase, RecipeOptions
from thirdparty.env import VirtualBuildEnv
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get, rmdir
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import Version, WebReleaseIndex


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libxau"
    version = "1.0.12"
    license = "MIT"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://www.x.org/releases/individual/lib/")
        return Version(index.latest_release(r"libXau-([\d.]+)\.tar\.xz"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        if self.settings.os not in ("Linux", "FreeBSD", "Android"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux-like platforms")

    def requirements(self):
        self.requires("xorg-proto")
        self.requires_tool("meson")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://www.x.org/releases/individual/lib/libXau-{self.version}.tar.xz",
            sha256="74d0e4dfa3d39ad8939e99bda37f5967aba528211076828464d2777d477fc0fb",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        PkgConfigDeps(self).generate()
        tc = MesonToolchain(self)
        tc.project_options["libdir"] = "lib"
        tc.generate()

    def build(self):
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        meson = Meson(self)
        meson.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("pkg_config_name", "xau")
        self.info.libs = ["Xau"]
        self.info.requires = ["xorg-proto::xproto"]
