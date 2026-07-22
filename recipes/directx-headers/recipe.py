import os

from thirdparty import RecipeBase
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, rmdir
from thirdparty.meson import Meson, MesonToolchain
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "directx-headers"
    version = "1.619.4"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "microsoft/DirectX-Headers")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("meson")

    def source(self):
        get(
            self,
            url=f"https://github.com/microsoft/DirectX-Headers/archive/refs/tags/v{self.version}.tar.gz",
            sha256="427c4c20bdeb06022d706ba24cb14838b62cca4456a6072e826d7ffa706a4b1a",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = MesonToolchain(self)
        tc.project_options["build-test"] = False
        tc.generate()
        VirtualBuildEnv(self).generate()

    def build(self):
        meson = Meson(self)
        meson.configure()
        meson.build()

    def package(self):
        copy(self, "LICENSE", self.folders.source, self.folders.package / "licenses")
        meson = Meson(self)
        meson.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        if self.settings.os == "Linux":
            self.info.includedirs.append(os.path.join("include", "wsl", "stubs"))
        self.info.libs = ["d3dx12-format-properties", "DirectX-Guids"]
        self.info.set_property("cmake_file_name", "DirectX-Headers")
        self.info.set_property("cmake_target_name", "Microsoft::DirectX-Headers")
        self.info.set_property("pkg_config_name", "DirectX-Headers")
        if self.settings.os == "Windows":
            self.info.system_libs.append("d3d12")
        if self.settings.compiler == "msvc":
            self.info.system_libs.append("dxcore")
