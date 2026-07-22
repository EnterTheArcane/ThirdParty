from thirdparty import RecipeBase, RecipeOptions
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import GithubRepository, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "vaapi"
    version = "2.24.1"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "intel/libva")
        return Version(repo.latest_formal_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        from thirdparty.errors import RecipeInvalidConfiguration
        if self.settings.os not in ("Linux", "FreeBSD"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux-like platforms")

    def requirements(self):
        self.requires_tool("meson")
        self.requires("libdrm")
        self.requires("libx11")
        self.requires("libxext")
        self.requires("libxfixes")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://github.com/intel/libva/releases/download/{self.version}/libva-{self.version}.tar.bz2",
            sha256="eec6050b52876f229bd35e9df17cd31a06785e18e6f7990c445b584628483d67",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        PkgConfigDeps(self).generate()
        tc = MesonToolchain(self)
        tc.project_options["libdir"] = "lib"
        tc.project_options["default_library"] = "shared" if self.options.shared else "static"
        tc.project_options["with_x11"] = "yes"
        tc.project_options["with_glx"] = "no"
        tc.project_options["with_wayland"] = "no"
        tc.project_options["enable_docs"] = False
        tc.generate()

    def build(self):
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        meson = Meson(self)
        meson.install()
        rm(self, "*.la", self.folders.package / "lib")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        # Core libva.
        va = self.info.components["vaapi"]
        va.set_property("pkg_config_name", "libva")
        va.libs = ["va"]
        if self.settings.os in ("Linux", "FreeBSD"):
            va.system_libs = ["dl", "m"]

        # libva-drm (DRM/KMS backend).
        va_drm = self.info.components["va-drm"]
        va_drm.set_property("pkg_config_name", "libva-drm")
        va_drm.libs = ["va-drm"]
        va_drm.requires = ["vaapi", "libdrm::libdrm_libdrm"]

        # libva-x11 (X11 backend).
        va_x11 = self.info.components["va-x11"]
        va_x11.set_property("pkg_config_name", "libva-x11")
        va_x11.libs = ["va-x11"]
        va_x11.requires = ["vaapi", "libx11::x11", "libxext::libxext", "libxfixes::libxfixes"]
