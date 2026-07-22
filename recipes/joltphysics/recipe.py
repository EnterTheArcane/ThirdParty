from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.microsoft import is_msvc, is_msvc_static_runtime
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "joltphysics"
    version = "5.6.0"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "jrouwe/JoltPhysics")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")
        if self.settings.os == "Linux":
            # Jolt compiles its Vulkan shaders with DXC and loads Vulkan at runtime.
            # DXC must run on the build machine when cross-compiling Linux ARM.
            self.requires_tool("directxshadercompiler")
            self.requires("vulkan-headers")
            self.requires("vulkan-loader")

    def source(self):
        get(
            self,
            url=f"https://github.com/jrouwe/JoltPhysics/archive/refs/tags/v{self.version}.tar.gz",
            sha256="6e069ee0172478cc78182047aac87e5310ba14a67a53348ae14cc37801fd3f8e",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["TARGET_UNIT_TESTS"] = False
        tc.cache_variables["TARGET_HELLO_WORLD"] = False
        tc.cache_variables["TARGET_PERFORMANCE_TEST"] = False
        tc.cache_variables["TARGET_SAMPLES"] = False
        tc.cache_variables["TARGET_VIEWER"] = False
        tc.cache_variables["JPH_BUILD_SHARED_LIBS"] = self.options.shared
        tc.cache_variables["ENABLE_OBJECT_STREAM"] = True
        # Use the native GPU compute backend where the complete shader toolchain is
        # available, while retaining Jolt's CPU implementation as a fallback.
        tc.cache_variables["JPH_USE_DX12"] = self.settings.os == "Windows"
        tc.cache_variables["JPH_USE_VK"] = self.settings.os == "Linux"
        tc.cache_variables["JPH_USE_MTL"] = False
        tc.cache_variables["JPH_USE_CPU_COMPUTE"] = True
        if self.settings.os == "Linux":
            dxc = self.dependencies.build["directxshadercompiler"].folders.package / "bin" / "dxc"
            # Jolt 5.6 derives dxc from FindVulkan's glslc path. Point that cache
            # entry directly at the packaged compiler; replacing "glslc" is then a no-op.
            tc.cache_variables["Vulkan_GLSLC_EXECUTABLE"] = dxc.as_posix()
        tc.cache_variables["CROSS_PLATFORM_DETERMINISTIC"] = False
        tc.cache_variables["INTERPROCEDURAL_OPTIMIZATION"] = False
        tc.cache_variables["GENERATE_DEBUG_SYMBOLS"] = False
        tc.cache_variables["ENABLE_ALL_WARNINGS"] = False
        tc.cache_variables["OVERRIDE_CXX_FLAGS"] = False
        tc.cache_variables["DEBUG_RENDERER_IN_DEBUG_AND_RELEASE"] = False
        tc.cache_variables["PROFILER_IN_DEBUG_AND_RELEASE"] = False
        if is_msvc(self):
            tc.cache_variables["USE_STATIC_MSVC_RUNTIME_LIBRARY"] = is_msvc_static_runtime(self)
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.source / "Build")
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rm(self, "*.cmake", self.folders.package / "include" / "Jolt")

    def package_info(self):
        self.info.libs = ["Jolt"]
        self.info.set_property("cmake_file_name", "Jolt")
        self.info.set_property("cmake_target_name", "Jolt::Jolt")
        self.info.defines = ["JPH_OBJECT_STREAM", "JPH_USE_CPU_COMPUTE"]
        if self.settings.os == "Windows":
            self.info.defines.append("JPH_USE_DX12")
            self.info.system_libs.extend(["dxgi", "d3d12", "d3dcompiler", "dxguid"])
        elif self.settings.os == "Linux":
            self.info.defines.append("JPH_USE_VK")
            self.info.requires = [
                "vulkan-headers::vulkan-headers",
                "vulkan-loader::vulkan-loader",
            ]
            self.info.resdirs = ["share"]
        if self.settings.arch in ["X64"]:
            self.info.defines.extend(
                [
                    "JPH_USE_AVX2", "JPH_USE_AVX", "JPH_USE_SSE4_1",
                    "JPH_USE_SSE4_2", "JPH_USE_LZCNT", "JPH_USE_TZCNT",
                    "JPH_USE_F16C", "JPH_USE_FMADD",
                ])
        if is_msvc(self):
            self.info.defines.append("JPH_FLOATING_POINT_EXCEPTIONS_ENABLED")
        if self.options.shared:
            self.info.defines.append("JPH_SHARED_LIBRARY")
        self.info.defines.append("JPH_OBJECT_LAYER_BITS=16")
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("pthread")
        if self.settings.os == "Linux":
            self.info.system_libs.append("dl")
