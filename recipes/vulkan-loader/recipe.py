from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, replace_in_file, rmdir
from thirdparty.pkgconfig import PkgConfigDeps
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = True
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "vulkan-loader"
    version = "1.4.350.1"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "KhronosGroup/Vulkan-Loader")
        return Version(repo.latest_tag("vulkan-sdk-").removeprefix("vulkan-sdk-"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("vulkan-headers")
        # The Linux loader uses PkgConfig to find the X11/XCB WSI system libraries.
        if self.settings.os in ("Linux", "FreeBSD"):
            self.requires("libxcb")
            self.requires("libx11")
            self.requires("libxrandr")
            if not self.conf.tools.gnu.pkg_config:
                self.requires_tool("pkgconf")

    def source(self):
        get(
            self,
            url=f"https://github.com/KhronosGroup/Vulkan-Loader/archive/refs/tags/vulkan-sdk-{self.version}.tar.gz",
            sha256="602984a71000981e25e4feb419e6cdd70b18ffe2b8004f60f591706027bca468",
            destination=self.folders.source,
            strip_root=True)
        replace_in_file(
            self,
            self.folders.source / "CMakeLists.txt",
            "set(CMAKE_MSVC_RUNTIME_LIBRARY \"MultiThreaded$<$<CONFIG:Debug>:Debug>\")",
            "")
        # Empty the genex-wrapped /W4 so the quiet -w wins without cl's D9025 spam.
        replace_in_file(
            self, self.folders.source / "CMakeLists.txt",
            "$<$<COMPILE_LANGUAGE::CXX,C>:/W4>", "$<$<COMPILE_LANGUAGE::CXX,C>:>", strict=False)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_TESTS"] = False
        tc.variables["LOADER_CODEGEN"] = False
        vulkan_headers = self.dependencies["vulkan-headers"].folders.package.as_posix()
        tc.variables["VULKAN_HEADERS_INSTALL_DIR"] = vulkan_headers
        tc.generate()
        deps = CMakeDeps(self)
        deps.generate()
        # X11/XCB WSI libraries are discovered via pkg-config on Linux.
        if self.settings.os in ("Linux", "FreeBSD"):
            VirtualBuildEnv(self).generate()
            PkgConfigDeps(self).generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "loader")

    def package_info(self):
        self.info.set_property("cmake_file_name", "VulkanLoader")
        self.info.set_property("cmake_target_name", "Vulkan::Loader")
        self.info.set_property("cmake_target_aliases", ["Vulkan::Vulkan"])
        self.info.includedirs = []
        if self.settings.os == "Windows":
            self.info.libs = ["vulkan-1"]
        else:
            self.info.libs = ["vulkan"]
