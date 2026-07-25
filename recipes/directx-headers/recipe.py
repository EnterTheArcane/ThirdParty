import os

from thirdparty import RecipeBase
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, rmdir
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
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/microsoft/DirectX-Headers/archive/refs/tags/v{self.version}.tar.gz",
            sha256="427c4c20bdeb06022d706ba24cb14838b62cca4456a6072e826d7ffa706a4b1a",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["BUILD_TESTING"] = False
        tc.cache_variables["DXHEADERS_BUILD_TEST"] = False
        tc.cache_variables["DXHEADERS_BUILD_GOOGLE_TEST"] = False
        tc.cache_variables["DXHEADERS_INSTALL"] = True
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", self.folders.source, self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        if self.settings.os != "Windows":
            self.info.includedirs.append(os.path.join("include", "wsl", "stubs"))
        self.info.libs = ["DirectX-Guids", "DirectX-Headers"]
        self.info.set_property("cmake_file_name", "DirectX-Headers")
        self.info.set_property("cmake_target_name", "Microsoft::DirectX-Headers")
        self.info.set_property("pkg_config_name", "DirectX-Headers")
        if self.settings.os == "Windows":
            self.info.system_libs.append("d3d12")
        if self.settings.compiler == "msvc":
            self.info.system_libs.append("dxcore")
