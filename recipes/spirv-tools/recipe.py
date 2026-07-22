from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import stdcpp_library
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.env import VirtualBuildEnv
from thirdparty.files import copy, get, replace_in_file, rm, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "spirv-tools"
    version = "1.4.350.1"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "KhronosGroup/SPIRV-Tools")
        return Version(repo.latest_tag("vulkan-sdk-").removeprefix("vulkan-sdk-"))

    def requirements(self):
        self.requires_tool("cmake")
        self.requires(f"spirv-headers")

    def source(self):
        get(
            self,
            url=f"https://github.com/KhronosGroup/SPIRV-Tools/archive/refs/tags/vulkan-sdk-{self.version}.tar.gz",
            sha256="6f7b9b9eed9a7aa485918466ea604b4edc7969d94e96c0c13ae266f4ec120f31",
            destination=self.folders.source,
            strip_root=True)
        replace_in_file(self, self.folders.source / "CMakeLists.txt", "set(CMAKE_POSITION_INDEPENDENT_CODE ON)", "")

    def generate(self):
        VirtualBuildEnv(self).generate()

        tc = CMakeToolchain(self)

        # ====================
        # Shared libs mess in Spirv-Tools (see https://github.com/KhronosGroup/SPIRV-Tools/issues/3909)
        # ====================
        # We have 2 solutions if shared True:
        #  - Only package SPIRV-Tools-shared lib (private symbols properly hidden), and wait resolution
        #    of above issue before allowing to build shared for all Spirv-Tools libs.
        #  - Build and package shared libs with all symbols exported
        #    (it would require CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS for msvc)
        # Currently this recipe implements the first solution

        # Static and shared libs are controlled by a weird combination
        # of SPIRV_TOOLS_BUILD_STATIC and BUILD_SHARED_LIBS.
        tc.variables["SPIRV_TOOLS_BUILD_STATIC"] = True
        # ============

        # Required by the project's CMakeLists.txt
        tc.variables["SPIRV-Headers_SOURCE_DIR"] = self.dependencies["spirv-headers"].folders.package.as_posix()

        # There are some switch( ) statements that are causing errors
        # need to turn this off
        tc.variables["SPIRV_WERROR"] = False

        tc.variables["SKIP_SPIRV_TOOLS_INSTALL"] = False
        tc.variables["SPIRV_LOG_DEBUG"] = False
        tc.variables["SPIRV_SKIP_TESTS"] = True
        tc.variables["SPIRV_CHECK_CONTEXT"] = False
        tc.variables["SPIRV_BUILD_FUZZER"] = False
        tc.variables["SPIRV_SKIP_EXECUTABLES"] = False
        # For iOS/tvOS/watchOS
        tc.variables["CMAKE_MACOSX_BUNDLE"] = False

        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "SPIRV-Tools")
        rmdir(self, self.folders.package / "SPIRV-Tools-link")
        rmdir(self, self.folders.package / "SPIRV-Tools-opt")
        rmdir(self, self.folders.package / "SPIRV-Tools-reduce")
        rmdir(self, self.folders.package / "SPIRV-Tools-lint")
        rmdir(self, self.folders.package / "SPIRV-Tools-diff")
        rmdir(self, self.folders.package / "SPIRV-Tools-tools")
        if self.options.shared:
            for file_name in [
                "*SPIRV-Tools", "*SPIRV-Tools-opt", "*SPIRV-Tools-link",
                "*SPIRV-Tools-reduce", "*SPIRV-Tools-lint",
            ]:
                for ext in [".a", ".lib"]:
                    rm(self, f"{file_name}{ext}", self.folders.package / "lib")
        else:
            rm(self, "*SPIRV-Tools-shared.dll", self.folders.package / "bin")
            rm(self, "*SPIRV-Tools-shared*", self.folders.package / "lib")

    def package_info(self):
        self.info.set_property("cmake_file_name", "SPIRV-Tools")
        self.info.set_property("pkg_config_name", "SPIRV-Tools-shared" if self.options.shared else "SPIRV-Tools")

        # SPIRV-Tools
        self.info.components["spirv-tools-core"].set_property(
            "cmake_target_name",
            "SPIRV-Tools-shared" if self.options.shared else "SPIRV-Tools-static",
        )
        self.info.components["spirv-tools-core"].set_property("cmake_target_aliases", ["SPIRV-Tools"])  # before 2020.5, kept for conveniency
        self.info.components["spirv-tools-core"].libs = ["SPIRV-Tools-shared" if self.options.shared else "SPIRV-Tools"]
        self.info.components["spirv-tools-core"].requires = ["spirv-headers::spirv-headers"]
        if self.options.shared:
            self.info.components["spirv-tools-core"].defines = ["SPIRV_TOOLS_SHAREDLIB"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["spirv-tools-core"].system_libs.extend(["m", "rt"])
        if not self.options.shared:
            libcxx = stdcpp_library(self)
            if libcxx:
                self.info.components["spirv-tools-core"].system_libs.append(libcxx)

        # FIXME: others components should have their own CMake config file
        if not self.options.shared:
            # SPIRV-Tools-opt
            self.info.components["spirv-tools-opt"].set_property("cmake_target_name", "SPIRV-Tools-opt")
            self.info.components["spirv-tools-opt"].libs = ["SPIRV-Tools-opt"]
            self.info.components["spirv-tools-opt"].requires = ["spirv-tools-core", "spirv-headers::spirv-headers"]
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.components["spirv-tools-opt"].system_libs.append("m")

            # SPIRV-Tools-link
            self.info.components["spirv-tools-link"].set_property("cmake_target_name", "SPIRV-Tools-link")
            self.info.components["spirv-tools-link"].libs = ["SPIRV-Tools-link"]
            self.info.components["spirv-tools-link"].requires = ["spirv-tools-core", "spirv-tools-opt"]

            # SPIRV-Tools-reduce
            self.info.components["spirv-tools-reduce"].set_property("cmake_target_name", "SPIRV-Tools-reduce")
            self.info.components["spirv-tools-reduce"].libs = ["SPIRV-Tools-reduce"]
            self.info.components["spirv-tools-reduce"].requires = ["spirv-tools-core", "spirv-tools-opt"]

            # SPIRV-Tools-lint
            self.info.components["spirv-tools-lint"].set_property("cmake_target_name", "SPIRV-Tools-lint")
            self.info.components["spirv-tools-lint"].libs = ["SPIRV-Tools-lint"]
            self.info.components["spirv-tools-lint"].requires = ["spirv-tools-core", "spirv-tools-opt"]

            # SPIRV-Tools-diff
            self.info.components["spirv-tools-diff"].set_property("cmake_target_name", "SPIRV-Tools-diff")
            self.info.components["spirv-tools-diff"].libs = ["SPIRV-Tools-diff"]
            self.info.components["spirv-tools-diff"].requires = ["spirv-tools-core", "spirv-tools-opt"]
