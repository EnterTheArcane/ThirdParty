from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import can_run
from thirdparty.env import VirtualBuildEnv, VirtualRunEnv
from thirdparty.files import apply_patches, copy, get, replace_in_file, rmdir
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.scm import Version
from thirdparty.scm.gitlab import GitlabRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    enable_libraries: bool


class Recipe(RecipeBase[_Options]):
    name = "wayland"
    version = "1.26.0"
    license = "MIT"

    def latest_version(self):
        repo = GitlabRepository(self, "wayland/wayland", host="gitlab.freedesktop.org")
        return Version(repo.latest_release)

    def configure(self):
        # enable libraries by defualt only on Linux, Android
        self.options.enable_libraries = self.settings.os in ("Linux", "Android")

        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def validate(self):
        from thirdparty.errors import RecipeInvalidConfiguration
        if self.settings.os == "Windows":
            raise RecipeInvalidConfiguration(f"{self.name} is not supported on Windows")

    def requirements(self):
        if self.options.enable_libraries:
            self.requires("libffi")
        self.requires("libxml2")
        self.requires("libexpat")
        self.requires_tool("meson")
        if not self.conf.tools.gnu.pkg_config:
            self.requires_tool("pkgconf")
        if not can_run(self):
            self.requires_tool(self.name)

    def source(self):
        get(
            self,
            url=f"https://gitlab.freedesktop.org/wayland/wayland/-/releases/{self.version}/downloads/wayland-{self.version}.tar.xz",
            sha256="64176eaa46e4969903e286f8e5ef8331affc17fdf03ac9b58381d2b23162b7a3",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)
        replace_in_file(self, self.folders.source / "meson.build", "subdir('tests')", "#subdir('tests')")

    def generate(self):
        VirtualBuildEnv(self).generate()
        if can_run(self):
            VirtualRunEnv(self).generate(scope="build")

        deps = PkgConfigDeps(self)
        if not can_run(self):
            deps.build_context_activated = ["wayland"]
        elif self.dependencies["libexpat"].is_build_context:  # wayland is being built as a tool
            # If wayland is a tool requirement, all its dependencies are in the build context
            deps.build_context_activated = [dep.name for _, dep in self.dependencies.host.items()]
        deps.generate()
        tc = MesonToolchain(self)
        tc.project_options["libdir"] = "lib"
        tc.project_options["datadir"] = "res"
        tc.project_options["libraries"] = self.options.enable_libraries
        tc.project_options["dtd_validation"] = True
        tc.project_options["documentation"] = False
        if not can_run(self):
            tc.project_options["build.pkg_config_path"] = self.folders.generators
        tc.project_options["scanner"] = True
        tc.generate()

    def build(self):
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        meson = Meson(self)
        meson.install()
        pkg_config_dir = self.folders.package / "lib" / "pkgconfig"
        rmdir(self, pkg_config_dir)

    def package_info(self):
        self.info.components["wayland-scanner"].set_property("pkg_config_name", "wayland-scanner")
        self.info.components["wayland-scanner"].resdirs = ["res"]
        self.info.components["wayland-scanner"].includedirs = []
        self.info.components["wayland-scanner"].libdirs = []
        self.info.components["wayland-scanner"].set_property("component_version", self.version)
        self.info.components["wayland-scanner"].requires = ["libexpat::libexpat"]
        self.info.components["wayland-scanner"].requires.append("libxml2::libxml2")
        pkgconfig_variables = {
            "datarootdir": "${prefix}/res",
            "pkgdatadir": "${datarootdir}/wayland",
            "bindir": "${prefix}/bin",
            "wayland_scanner": "${bindir}/wayland-scanner",
        }
        self.info.components["wayland-scanner"].set_property(
            "pkg_config_custom_content",
            "\n".join(f"{key}={value}" for key, value in pkgconfig_variables.items()))

        if self.options.enable_libraries:
            self.info.components["wayland-server"].libs = ["wayland-server"]
            self.info.components["wayland-server"].set_property("pkg_config_name", "wayland-server")
            self.info.components["wayland-server"].requires = ["libffi::libffi"]
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.components["wayland-server"].system_libs = ["pthread", "m"]

            self.info.components["wayland-server"].resdirs = ["res"]
            if self.settings.os == "Linux":
                self.info.components["wayland-server"].system_libs += ["rt"]
            self.info.components["wayland-server"].set_property("component_version", self.version)
            pkgconfig_variables = {
                "datarootdir": "${prefix}/res",
                "pkgdatadir": "${datarootdir}/wayland",
            }
            self.info.components["wayland-server"].set_property(
                "pkg_config_custom_content",
                "\n".join(f"{key}={value}" for key, value in pkgconfig_variables.items()))

            self.info.components["wayland-client"].libs = ["wayland-client"]
            self.info.components["wayland-client"].set_property("pkg_config_name", "wayland-client")
            self.info.components["wayland-client"].requires = ["libffi::libffi"]
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.components["wayland-client"].system_libs = ["pthread", "m"]
            self.info.components["wayland-client"].resdirs = ["res"]
            if self.settings.os == "Linux":
                self.info.components["wayland-client"].system_libs += ["rt"]
            self.info.components["wayland-client"].set_property("component_version", self.version)
            pkgconfig_variables = {
                "datarootdir": "${prefix}/res",
                "pkgdatadir": "${datarootdir}/wayland",
            }
            self.info.components["wayland-client"].set_property(
                "pkg_config_custom_content",
                "\n".join(f"{key}={value}" for key, value in pkgconfig_variables.items()))

            self.info.components["wayland-cursor"].libs = ["wayland-cursor"]
            self.info.components["wayland-cursor"].set_property("pkg_config_name", "wayland-cursor")
            self.info.components["wayland-cursor"].requires = ["wayland-client"]
            self.info.components["wayland-cursor"].set_property("component_version", self.version)

            self.info.components["wayland-egl"].libs = ["wayland-egl"]
            self.info.components["wayland-egl"].set_property("pkg_config_name", "wayland-egl")
            self.info.components["wayland-egl"].requires = ["wayland-client"]
            self.info.components["wayland-egl"].set_property("component_version", "18.1.0")

            self.info.components["wayland-egl-backend"].set_property("pkg_config_name", "wayland-egl-backend")
            self.info.components["wayland-egl-backend"].set_property("component_version", "3")
