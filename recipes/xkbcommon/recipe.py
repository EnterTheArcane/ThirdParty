from thirdparty import RecipeBase, RecipeOptions
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rmdir
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import GithubRepository, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    with_x11: bool = True
    with_wayland: bool = False


class Recipe(RecipeBase[_Options]):
    name = "xkbcommon"
    version = "1.13.2"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "xkbcommon/libxkbcommon")
        return Version(repo.latest_release.removeprefix("xkbcommon-"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        from thirdparty.errors import RecipeInvalidConfiguration
        if self.settings.os not in ("Linux", "FreeBSD", "Android"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux-like platforms")

    def requirements(self):
        if self.options.with_x11:
            self.requires("libxcb")
        self.requires_tool("meson")
        self.requires_tool("bison")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://github.com/xkbcommon/libxkbcommon/archive/refs/tags/xkbcommon-{self.version}.tar.gz",
            sha256="acc4d5f7c3cbba5f9f8d08d8bdbeede84ecede46792f47929aa9321873385528",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        PkgConfigDeps(self).generate()
        tc = MesonToolchain(self)
        tc.project_options["libdir"] = "lib"
        tc.project_options["enable-x11"] = self.options.with_x11
        tc.project_options["enable-wayland"] = self.options.with_wayland
        tc.project_options["enable-docs"] = False
        tc.project_options["enable-xkbregistry"] = False
        tc.project_options["enable-tools"] = False
        tc.generate()

    def build(self):
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        meson = Meson(self)
        meson.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        # Qt's installed Qt6GuiConfig.cmake calls find_dependency(XKB) and consumes XKB::XKB.
        # Export that canonical interface here so every native Qt CMake consumer gets it from
        # CMakeDeps instead of synthesizing an ad-hoc compatibility file.
        self.info.set_property("cmake_file_name", "XKB")
        # Qt asks for XKB 0.9.0. xkbcommon's stable API is intentionally compatible
        # across the 0.x -> 1.x boundary, so CMake's default SameMajorVersion policy
        # would incorrectly reject this package even though it is new enough.
        self.info.set_property("cmake_config_version_compat", "AnyNewerVersion")
        xkb = self.info.components["xkbcommon"]
        xkb.set_property("cmake_target_name", "XKB::XKB")
        xkb.set_property("pkg_config_name", "xkbcommon")
        xkb.libs = ["xkbcommon"]
        if self.settings.os in ("Linux", "FreeBSD"):
            xkb.system_libs = ["m"]

        if self.options.with_x11:
            self.info.components["libxkbcommon-x11"].set_property("pkg_config_name", "xkbcommon-x11")
            self.info.components["libxkbcommon-x11"].libs = ["xkbcommon-x11"]
            self.info.components["libxkbcommon-x11"].requires = ["xkbcommon", "libxcb::xcb", "libxcb::xkb"]
