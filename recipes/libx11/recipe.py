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
    name = "libx11"
    version = "1.8.13"
    license = "MIT"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://www.x.org/releases/individual/lib/")
        return Version(index.latest_release(r"libX11-([\d.]+)\.tar\.xz"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        from thirdparty.errors import RecipeInvalidConfiguration
        if self.settings.os not in ("Linux", "FreeBSD", "Android"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux-like platforms")

    def requirements(self):
        self.requires("xorg-proto")
        self.requires("xtrans")
        self.requires("libxcb")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://www.x.org/releases/individual/lib/libX11-{self.version}.tar.xz",
            sha256="69606f485c2c07c14ef64f75b7bb326d48587af33795d9ab3e607c0b5f94f11c",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        PkgConfigDeps(self).generate()
        tc = AutotoolsToolchain(self)
        tc.configure_args.append("--disable-specs")
        tc.configure_args.append("--without-xmlto")
        tc.configure_args.append("--without-fop")
        tc.configure_args.append("--without-xsltproc")
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
        self.info.components["x11"].set_property("pkg_config_name", "x11")
        self.info.components["x11"].libs = ["X11"]
        self.info.components["x11"].requires = ["xorg-proto::xproto", "libxcb::xcb"]
        if self.settings.os in ("Linux", "FreeBSD"):
            self.info.components["x11"].system_libs = ["dl"]

        self.info.components["x11-xcb"].set_property("pkg_config_name", "x11-xcb")
        self.info.components["x11-xcb"].libs = ["X11-xcb"]
        self.info.components["x11-xcb"].requires = ["x11", "libxcb::xcb"]
