from thirdparty import RecipeBase, RecipeOptions
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import Version, WebReleaseIndex

# Each xcb-* library libxcb builds installs its own <name>.pc; expose them as components so
# consumers (libX11, vulkan-loader, ...) can require just the ones they need.
_COMPONENTS = {
    "xcb": "xcb",
    "composite": "xcb-composite",
    "damage": "xcb-damage",
    "dbe": "xcb-dbe",
    "dpms": "xcb-dpms",
    "dri2": "xcb-dri2",
    "dri3": "xcb-dri3",
    "glx": "xcb-glx",
    "present": "xcb-present",
    "randr": "xcb-randr",
    "record": "xcb-record",
    "render": "xcb-render",
    "res": "xcb-res",
    "screensaver": "xcb-screensaver",
    "shape": "xcb-shape",
    "shm": "xcb-shm",
    "sync": "xcb-sync",
    "xf86dri": "xcb-xf86dri",
    "xfixes": "xcb-xfixes",
    "xinerama": "xcb-xinerama",
    "xinput": "xcb-xinput",
    "xkb": "xcb-xkb",
    "xtest": "xcb-xtest",
    "xv": "xcb-xv",
    "xvmc": "xcb-xvmc",
}


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libxcb"
    version = "1.17.0"
    license = "MIT"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://xorg.freedesktop.org/releases/individual/lib/")
        return Version(index.latest_release(r"libxcb-([\d.]+)\.tar\.xz"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        from thirdparty.errors import RecipeInvalidConfiguration
        if self.settings.os not in ("Linux", "FreeBSD", "Android"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux-like platforms")

    def requirements(self):
        self.requires("xcb-proto")
        self.requires("libxau")
        self.requires("libxdmcp")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://xorg.freedesktop.org/releases/individual/lib/libxcb-{self.version}.tar.xz",
            sha256="599ebf9996710fea71622e6e184f3a8ad5b43d0e5fa8c4e407123c88a59a6d55",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        PkgConfigDeps(self).generate()
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
        for comp, pcname in _COMPONENTS.items():
            c = self.info.components[comp]
            c.set_property("pkg_config_name", pcname)
            c.set_property("component_version", self.version)
            c.libs = [f"xcb-{comp}" if comp != "xcb" else "xcb"]
            if self.settings.os in ("Linux", "FreeBSD"):
                c.system_libs = ["pthread"]

        # Inter-library dependencies (subset that matters to downstream consumers).
        self.info.components["xcb"].requires = ["libxau::libxau", "libxdmcp::libxdmcp"]
        for comp in _COMPONENTS:
            if comp != "xcb":
                self.info.components[comp].requires = ["xcb"]
