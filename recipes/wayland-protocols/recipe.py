import os

from thirdparty import RecipeBase
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, replace_in_file, rmdir
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.scm import Version
from thirdparty.scm.gitlab import GitlabRepository


class Recipe(RecipeBase):
    name = "wayland-protocols"
    version = "1.49"
    license = "MIT"

    def latest_version(self):
        repo = GitlabRepository(self, "wayland/wayland-protocols", host="gitlab.freedesktop.org")
        return Version(repo.latest_release)

    def requirements(self):
        self.requires_tool("meson")

    def source(self):
        get(
            self,
            url=f"https://gitlab.freedesktop.org/wayland/wayland-protocols/-/releases/{self.version}/downloads/wayland-protocols-{self.version}.tar.xz",
            sha256="ec4c8f74942d6dff7ace8b4ce4764f0ef9ff618a935d974ea77edee2ad240b14",
            destination=self.folders.source,
            strip_root=True)
        replace_in_file(
            self,
            self.folders.source / "meson.build",
            "dep_scanner = dependency('wayland-scanner',",
            "dep_scanner = dependency('wayland-scanner', required: false, disabler: true,")

    def generate(self):
        tc = MesonToolchain(self)
        # Using relative folder because of this upstream PR 15706
        tc.project_options["datadir"] = "res"
        tc.project_options["tests"] = "false"
        tc.generate()
        VirtualBuildEnv(self).generate()

    def build(self):
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, "COPYING", self.folders.source, self.folders.package / "licenses")
        meson = Meson(self)
        meson.install()
        rmdir(self, self.folders.package / "res" / "pkgconfig")

    def package_info(self):
        self.info.libdirs = []
        self.info.includedirs = []
        self.info.bindirs = []
        # Consumers (e.g. vulkan-tools' cube) locate the protocol XML via
        # `pkg-config --variable=pkgdatadir wayland-protocols`.
        self.info.set_property("pkg_config_name", "wayland-protocols")
        self.info.set_property(
            "pkg_config_custom_content",
            f"pkgdatadir={os.path.join(self.folders.package, 'res', 'wayland-protocols')}")
