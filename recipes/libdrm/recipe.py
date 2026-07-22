from thirdparty import RecipeBase, RecipeOptions
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import Version, WebReleaseIndex


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libdrm"
    version = "2.4.134"
    license = "MIT"

    def latest_version(self):
        index = WebReleaseIndex(self, "https://dri.freedesktop.org/libdrm/")
        return Version(index.latest_release(r"libdrm-([\d.]+)\.tar\.xz"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        from thirdparty.errors import RecipeInvalidConfiguration
        if self.settings.os not in ("Linux", "FreeBSD"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux-like platforms")

    def requirements(self):
        self.requires_tool("meson")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://dri.freedesktop.org/libdrm/libdrm-{self.version}.tar.xz",
            sha256="ac5e74d157830eb8bee44c6a6bf3ad49774ef0dd2a72bdad74a8f20308b52a95",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        PkgConfigDeps(self).generate()
        tc = MesonToolchain(self)
        tc.project_options["libdir"] = "lib"
        tc.project_options["default_library"] = "shared" if self.options.shared else "static"
        # Only the core libdrm (drm.h / libdrm.so) is needed by consumers such as ffmpeg/libva;
        # disable all GPU-vendor drivers (and their extra deps) plus tests/docs.
        for driver in ("intel", "radeon", "amdgpu", "nouveau", "vmwgfx", "omap",
                       "exynos", "freedreno", "tegra", "vc4", "etnaviv"):
            tc.project_options[driver] = "disabled"
        tc.project_options["cairo-tests"] = "disabled"
        tc.project_options["man-pages"] = "disabled"
        tc.project_options["valgrind"] = "disabled"
        tc.project_options["tests"] = False
        tc.project_options["install-test-programs"] = False
        tc.generate()

    def build(self):
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, "LICENSE.TXT", src=self.folders.source, dst=self.folders.package / "licenses")
        meson = Meson(self)
        meson.install()
        rm(self, "*.la", self.folders.package / "lib")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("pkg_config_name", "libdrm_full_package")  # unused aggregate
        drm = self.info.components["libdrm_libdrm"]
        drm.set_property("pkg_config_name", "libdrm")
        drm.libs = ["drm"]
        drm.includedirs = ["include", "include/libdrm"]
        if self.settings.os in ("Linux", "FreeBSD"):
            drm.system_libs = ["m", "rt"]
