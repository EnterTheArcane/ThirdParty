from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "spirv-reflect"
    version = "1.4.350.1"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "KhronosGroup/SPIRV-Reflect")
        return Version(repo.latest_tag("vulkan-sdk-").removeprefix("vulkan-sdk-"))

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("spirv-headers")

    def source(self):
        get(
            self,
            url=f"https://github.com/KhronosGroup/SPIRV-Reflect/archive/refs/tags/vulkan-sdk-{self.version}.tar.gz",
            sha256="e045cdd7598211cdbaf39791151bc526a9844401d615579e4959966d2317bdd7",
            destination=self.folders.source,
            strip_root=True)
        # Empty the genex-wrapped /W4 /WX so the quiet -w wins without cl's D9025 spam.
        replace_in_file(
            self, self.folders.source / "CMakeLists.txt",
            "$<$<CXX_COMPILER_ID:MSVC>:/W4 /WX>", "$<$<CXX_COMPILER_ID:MSVC>:>", strict=False)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["SPIRV_REFLECT_STATIC_LIB"] = True
        tc.variables["SPIRV_REFLECT_EXAMPLES"] = False
        tc.variables["SPIRV_REFLECT_BUILD_TESTS"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.set_property("cmake_file_name", "spirv-reflect-static")
        self.info.set_property("cmake_target_name", "spirv-reflect-static")
        self.info.libs = ["spirv-reflect-static"]
        self.info.defines.append("SPIRV_REFLECT_USE_SYSTEM_SPIRV_H")
