from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name
from thirdparty.autotools import Autotools, AutotoolsToolchain
from thirdparty.env import VirtualBuildEnv
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import apply_patches, copy, get, rm, rmdir
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    pthread: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libverto"
    version = "0.3.2"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "latchset/libverto")
        return Version(repo.latest_release)

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        if self.settings.os == "Windows":
            raise RecipeInvalidConfiguration(f"{self.name} is not supported on Windows")

    def requirements(self):
        self.requires_tool("libtool")
        self.requires("libevent")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://github.com/latchset/libverto/releases/download/{self.version}/libverto-{self.version}.tar.gz",
            sha256="8d1756fd704f147549f606cd987050fb94b0b1ff621ea6aa4d6bf0b74450468a",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        VirtualBuildEnv(self).generate()
        PkgConfigDeps(self).generate()

        tc = AutotoolsToolchain(self)
        tc.configure_args.extend([
            "--enable-shared" if self.options.shared else "--disable-shared",
            "--disable-static" if self.options.shared else "--enable-static",
            f"--with-pthread={tc.yes_no("pthread")}",
            "--with-glib=no",
            "--with-libev=no",
            "--with-libevent=builtin",
            "--with-tevent=no",
        ])
        tc.generate()

    def build(self):
        autotools = Autotools(self)
        autotools.autoreconf()
        autotools.configure()
        autotools.make()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        Autotools(self).install()
        fix_apple_shared_install_name(self)
        rm(self, "*.la", self.folders.package / "lib")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.components["verto"].set_property("pkg_config_name", "libverto")
        self.info.components["verto"].libs = ["verto"]
        self.info.components["verto"].requires = ["libevent::core"]
        if self.settings.os == "Linux":
            self.info.components["verto"].system_libs.append("dl")
            if self.options.pthread:
                self.info.components["verto"].system_libs.append("pthread")
