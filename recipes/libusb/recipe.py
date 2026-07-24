from thirdparty import RecipeBase, RecipeOptions
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.env import VirtualBuildEnv
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libusb"
    version = "1.0.30"
    license = "LGPL-2.1-or-later"

    def latest_version(self):
        repo = GithubRepository(self, "libusb/libusb")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        if self.settings.os not in ("Linux", "FreeBSD"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux-like platforms")

    def requirements(self):
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://github.com/libusb/libusb/releases/download/v{self.version}/libusb-{self.version}.tar.bz2",
            sha256="fea36f34f9156400209595e300840767ab1a385ede1dc7ee893015aea9c6dbaf",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        tc = AutotoolsToolchain(self)
        # Enumerate USB devices via sysfs so libusb needs neither a system nor a vendored libudev
        # (hidapi's libusb backend does not depend on libusb's udev-based hotplug). Keeps the
        # library self-contained apart from pthread.
        tc.configure_args.append("--disable-udev")
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

    def package_info(self):
        libusb = self.info.components["libusb"]
        libusb.set_property("pkg_config_name", "libusb-1.0")
        libusb.libs = ["usb-1.0"]
        libusb.includedirs = ["include/libusb-1.0"]
        if self.settings.os in ("Linux", "FreeBSD"):
            libusb.system_libs = ["pthread"]
