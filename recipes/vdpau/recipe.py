from thirdparty import RecipeBase, RecipeOptions
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, replace_in_file, rm, rmdir
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import GitlabRepository, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "vdpau"
    version = "1.5"
    license = "MIT"

    def latest_version(self):
        repo = GitlabRepository(self, "vdpau/libvdpau", host="gitlab.freedesktop.org")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        from thirdparty.errors import RecipeInvalidConfiguration
        if self.settings.os not in ("Linux", "FreeBSD"):
            raise RecipeInvalidConfiguration(f"{self.name} is only supported on Linux-like platforms")

    def requirements(self):
        self.requires_tool("meson")
        self.requires("xorg-proto")
        self.requires("libx11")
        self.requires("libxext")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"http://deb.debian.org/debian/pool/main/libv/libvdpau/libvdpau_{self.version}.orig.tar.bz2",
            sha256="a5d50a42b8c288febc07151ab643ac8de06a18446965c7241f89b4e810821913",
            destination=self.folders.source,
            strip_root=True)
        # The trace module includes vdpau_x11.h (-> X11/Xlib.h) but only declares libdl, relying on
        # X11 headers being in the system default path. Our libx11 headers live in its package, so
        # declare the x11 dependency explicitly on the trace target too.
        replace_in_file(
            self,
            self.folders.source / "trace" / "meson.build",
            "dependencies : libdl,",
            "dependencies : [libdl, dependency('x11')],",
            strict=False)

    def generate(self):
        VirtualBuildEnv(self).generate()
        PkgConfigDeps(self).generate()
        tc = MesonToolchain(self)
        tc.project_options["libdir"] = "lib"
        tc.project_options["default_library"] = "shared" if self.options.shared else "static"
        tc.project_options["documentation"] = "false"
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
        self.info.set_property("pkg_config_name", "vdpau")
        self.info.libs = ["vdpau"]
        self.info.requires = ["libx11::x11", "libxext::libxext", "xorg-proto::xproto"]
        if self.settings.os in ("Linux", "FreeBSD"):
            self.info.system_libs = ["dl"]
