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
    # libudev is vendored from eudev, the standalone udev fork, so it does not depend on a system
    # libudev / systemd (mirrors how the X11 libraries are vendored from source).
    name = "libudev"
    version = "3.2.14"
    license = "GPL-2.0-or-later", "LGPL-2.1-or-later"

    def latest_version(self):
        repo = GithubRepository(self, "eudev-project/eudev")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        if self.settings.os != "Linux":
            raise RecipeInvalidConfiguration(f"{self.name} (eudev) is only supported on Linux")

    def requirements(self):
        self.requires_tool("gperf")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://github.com/eudev-project/eudev/releases/download/v{self.version}/eudev-{self.version}.tar.gz",
            sha256="8da4319102f24abbf7fff5ce9c416af848df163b29590e666d334cc1927f006f",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        tc = AutotoolsToolchain(self)
        # Build only libudev: skip udevd/udevadm and every optional external dependency so the
        # library is self-contained (no blkid, kmod, selinux or system udev/systemd).
        tc.configure_args.extend([
            "--disable-programs",
            "--disable-manpages",
            "--disable-hwdb",
            "--disable-kmod",
            "--disable-blkid",
            "--disable-selinux",
            "--disable-mtd_probe",
            "--disable-rule-generator",
        ])
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
        rmdir(self, self.folders.package / "etc")

    def package_info(self):
        libudev = self.info.components["libudev"]
        libudev.set_property("pkg_config_name", "libudev")
        libudev.libs = ["udev"]
        if self.settings.os in ("Linux", "FreeBSD"):
            libudev.system_libs = ["rt", "pthread"]
