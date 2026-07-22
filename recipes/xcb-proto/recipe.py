import glob
import os

from thirdparty import RecipeBase
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rmdir
from thirdparty.scm import Version, WebReleaseIndex


class Recipe(RecipeBase):
    name = "xcb-proto"
    version = "1.17.0"
    license = "MIT"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://xorg.freedesktop.org/releases/individual/xcb/")
        return Version(index.latest_release(r"xcb-proto-([\d.]+)\.tar\.xz"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        from thirdparty.errors import RecipeInvalidConfiguration
        if self.settings.os not in ("Linux", "FreeBSD", "Android"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux-like platforms")

    def requirements(self):
        self.requires_tool("meson")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://xorg.freedesktop.org/releases/individual/xcb/xcb-proto-{self.version}.tar.xz",
            sha256="2c1bacd2110f4799f74de6ebb714b94cf6f80fb112316b1219480fd22562148c",
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
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.bindirs = []
        self.info.libdirs = []
        self.info.includedirs = []
        self.info.set_property("pkg_config_name", "xcb-proto")
        # libxcb's Makefile reads two custom pkg-config variables of xcb-proto:
        #   xcbincludedir -> the protocol XML directory (passed to c_client.py)
        #   pythondir     -> the dir containing the xcbgen Python module (c_client.py's -p arg)
        # Both must be present or c_client.py mis-parses its arguments. The xcbgen install path
        # depends on the interpreter's sysconfig scheme (Ubuntu: local/.../dist-packages), so
        # locate it rather than hardcoding.
        content = [f"xcbincludedir={os.path.join(self.folders.package, 'share', 'xcb')}"]
        matches = glob.glob(os.path.join(self.folders.package, "**", "xcbgen"), recursive=True)
        if matches:
            pydir = os.path.dirname(matches[0])
            content.append(f"pythondir={pydir}")
            self.info.buildenv.prepend_path("PYTHONPATH", pydir)
        self.info.set_property("pkg_config_custom_content", "\n".join(content))
