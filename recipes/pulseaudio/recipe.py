from thirdparty import RecipeBase, RecipeOptions
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import GitlabRepository, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "pulseaudio"
    version = "17.0"
    license = "LGPL-2.1-or-later"

    def latest_version(self):
        repo = GitlabRepository(self, "pulseaudio/pulseaudio", host="gitlab.freedesktop.org")
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
        self.requires_tool("m4")
        self.requires("libsndfile")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://freedesktop.org/software/pulseaudio/releases/pulseaudio-{self.version}.tar.xz",
            sha256="053794d6671a3e397d849e478a80b82a63cb9d8ca296bd35b73317bb5ceb87b5",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        VirtualBuildEnv(self).generate()
        PkgConfigDeps(self).generate()
        tc = MesonToolchain(self)
        tc.project_options["libdir"] = "lib"
        tc.project_options["default_library"] = "shared" if self.options.shared else "static"
        # Consumers (ffmpeg) only need the libpulse client library. Skip the daemon, its modules and
        # their many external dependencies (libsndfile, tdb, dbus, X11, ...).
        tc.project_options["daemon"] = False
        tc.project_options["doxygen"] = False
        tc.project_options["man"] = False
        tc.project_options["tests"] = False
        tc.project_options["gcov"] = False
        tc.project_options["database"] = "simple"
        for feature in ("alsa", "asyncns", "avahi", "bluez5", "consolekit", "dbus", "elogind",
                        "fftw", "glib", "gsettings", "gstreamer", "gtk", "jack", "lirc", "openssl",
                        "orc", "oss-output", "samplerate", "soxr", "speex", "systemd", "tcpwrap",
                        "udev", "valgrind", "x11", "webrtc-aec"):
            tc.project_options[feature] = "disabled"
        tc.generate()

    def build(self):
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "GPL", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "LGPL", src=self.folders.source, dst=self.folders.package / "licenses")
        meson = Meson(self)
        meson.install()
        rm(self, "*.la", self.folders.package / "lib")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "share")
        rmdir(self, self.folders.package / "etc")

    def package_info(self):
        self.info.set_property("pkg_config_name", "libpulse")
        self.info.libs = ["pulse"]
        self.info.includedirs = ["include"]
        # libpulse.so has a private DT_NEEDED on libpulsecommon-<ver>.so, which meson installs into
        # the lib/pulseaudio subdir. Expose that dir so the linker (and -rpath-link) can resolve it
        # when consumers such as ffmpeg link against libpulse.
        self.info.libdirs = ["lib", "lib/pulseaudio"]
        if self.settings.os in ("Linux", "FreeBSD"):
            self.info.system_libs = ["pthread", "m", "rt", "dl"]
