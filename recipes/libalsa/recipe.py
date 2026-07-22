from thirdparty import RecipeBase, RecipeOptions
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.scm import Version, WebReleaseIndex


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libalsa"
    version = "1.2.16.1"
    license = "LGPL-2.1-or-later"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://www.alsa-project.org/files/pub/lib/")
        return Version(index.latest_release(r"alsa-lib-([\d.]+)\.tar\.bz2"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        from thirdparty.errors import RecipeInvalidConfiguration
        if self.settings.os not in ("Linux", "FreeBSD"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux-like platforms")

    def source(self):
        get(
            self,
            url=f"https://www.alsa-project.org/files/pub/lib/alsa-lib-{self.version}.tar.bz2",
            sha256="f740db7f488255944ffd4428416ee3390a96742856916433df468c281436480e",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        tc = AutotoolsToolchain(self)
        tc.configure_args.append("--disable-python")
        tc.configure_args.append("--disable-topology")
        tc.configure_args.append("--without-debug")
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
        self.info.set_property("pkg_config_name", "alsa")
        self.info.libs = ["asound"]
        if self.settings.os in ("Linux", "FreeBSD"):
            self.info.system_libs = ["dl", "m", "pthread", "rt"]
