from thirdparty import RecipeBase
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "spirv-headers"
    version = "1.4.350.1"
    license = "MIT-KhronosGroup"

    def latest_version(self):
        repo = GithubRepository(self, "KhronosGroup/SPIRV-Headers")
        return Version(repo.latest_tag("vulkan-sdk-").removeprefix("vulkan-sdk-"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/KhronosGroup/SPIRV-Headers/archive/refs/tags/vulkan-sdk-{self.version}.tar.gz",
            sha256="9e6d5c78878172d2b810e97f3a74ecbbb14b4ad52b07384ce915fbbeb226d610",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["SPIRV_HEADERS_SKIP_EXAMPLES"] = True
        tc.variables["SPIRV_HEADERS_ENABLE_TESTS"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "SPIRV-Headers")
        self.info.set_property("cmake_target_name", "SPIRV-Headers::SPIRV-Headers")
        self.info.set_property("pkg_config_name", "SPIRV-Headers")
        self.info.bindirs = []
        self.info.libdirs = []
