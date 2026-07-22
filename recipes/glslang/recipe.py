from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, rmdir, save
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    build_executables: bool = False
    enable_optimizer: bool = True


class Recipe(RecipeBase[_Options]):
    name = "glslang"
    version = "1.4.350.1"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "KhronosGroup/glslang")
        return Version(repo.latest_tag("vulkan-sdk-").removeprefix("vulkan-sdk-"))

    def requirements(self):
        self.requires_tool("cmake")
        if self.options.enable_optimizer:
            self.requires("spirv-tools")

    def source(self):
        get(
            self,
            url=f"https://github.com/KhronosGroup/glslang/archive/refs/tags/vulkan-sdk-{self.version}.tar.gz",
            sha256="da3224092779d09e275a993b5d2fe2c178847d1a4a5c802082ab99628c159c20",
            destination=self.folders.source / "src",
            strip_root=True)
        wrapper = (
            "cmake_minimum_required(VERSION 3.15)\n"
            "project(cmake_wrapper)\n"
            "if(ENABLE_OPT)\n"
            "    find_package(SPIRV-Tools REQUIRED CONFIG)\n"
            "endif()\n"
            "add_subdirectory(src)\n"
        )
        save(self, self.folders.source / "CMakeLists.txt", wrapper)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_SHARED_LIBS"] = self.options.shared
        tc.variables["GLSLANG_ENABLE_INSTALL"] = True
        tc.variables["ENABLE_GLSLANG_BINARIES"] = self.options.build_executables
        tc.variables["ENABLE_HLSL"] = True
        tc.variables["ENABLE_RTTI"] = True
        tc.variables["ENABLE_OPT"] = self.options.enable_optimizer
        tc.variables["ENABLE_SPVREMAPPER"] = False
        tc.variables["ENABLE_CTEST"] = False
        if self.options.enable_optimizer:
            spirv_tools_pkg = self.dependencies["spirv-tools"].folders.package
            tc.variables["spirv-tools_SOURCE_DIR"] = spirv_tools_pkg.as_posix()
        tc.generate()
        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        src = self.folders.source / "src"
        copy(self, "LICENSE*", src=src, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "glslang")

        self.info.components["glslang-core"].set_property("cmake_target_name", "glslang::glslang")
        self.info.components["glslang-core"].libs = ["glslang"]
        self.info.components["glslang-core"].requires = ["osdependent", "machineindependent", "genericcodegen"]
        if self.settings.os == "Windows":
            self.info.components["glslang-core"].system_libs = ["psapi"]
        elif self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["glslang-core"].system_libs = ["m", "pthread"]

        if not self.options.shared:
            self.info.components["osdependent"].set_property("cmake_target_name", "glslang::OSDependent")
            self.info.components["osdependent"].libs = ["OSDependent"]

            self.info.components["machineindependent"].set_property("cmake_target_name", "glslang::MachineIndependent")
            self.info.components["machineindependent"].libs = ["MachineIndependent"]
            self.info.components["machineindependent"].requires = ["osdependent", "genericcodegen"]

            self.info.components["genericcodegen"].set_property("cmake_target_name", "glslang::GenericCodeGen")
            self.info.components["genericcodegen"].libs = ["GenericCodeGen"]

        self.info.components["spirv"].set_property("cmake_target_name", "glslang::SPIRV")
        self.info.components["spirv"].libs = ["SPIRV"]
        self.info.components["spirv"].requires = ["glslang-core"]

        self.info.components["glslang-default-resource-limits"].set_property(
            "cmake_target_name", "glslang::glslang-default-resource-limits")
        self.info.components["glslang-default-resource-limits"].libs = ["glslang-default-resource-limits"]
