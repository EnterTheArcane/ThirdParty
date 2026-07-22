import os
from pathlib import Path
import textwrap

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import stdcpp_library
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, rm, rmdir, save
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    build_executable: bool = True
    exceptions: bool = True
    glsl: bool = True
    hlsl: bool = True
    msl: bool = True
    cpp: bool = True
    reflect: bool = True
    c_api: bool = True
    util: bool = True
    namespace: str = "spirv_cross"


class Recipe(RecipeBase[_Options]):
    name = "spirv-cross"
    version = "1.4.350.1"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "KhronosGroup/SPIRV-Cross")
        return Version(repo.latest_tag("vulkan-sdk-").removeprefix("vulkan-sdk-"))

    def configure(self):
        if self.options.shared:
            # util does not contribute to the shared binary
            self.options.util = False

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/KhronosGroup/SPIRV-Cross/archive/refs/tags/vulkan-sdk-{self.version}.tar.gz",
            sha256="21057934ede32fe90a63dc304fdce0f2a6cb4f0ca685a72ed36a73aac6f72ad5",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["SPIRV_CROSS_EXCEPTIONS_TO_ASSERTIONS"] = not self.options.exceptions
        tc.variables["SPIRV_CROSS_SHARED"] = self.options.shared
        tc.variables["SPIRV_CROSS_STATIC"] = not self.options.shared or self.options.build_executable
        tc.variables["SPIRV_CROSS_CLI"] = self.options.build_executable
        tc.variables["SPIRV_CROSS_ENABLE_TESTS"] = False
        tc.variables["SPIRV_CROSS_ENABLE_GLSL"] = self.options.glsl
        tc.variables["SPIRV_CROSS_ENABLE_HLSL"] = self.options.hlsl
        tc.variables["SPIRV_CROSS_ENABLE_MSL"] = self.options.msl
        tc.variables["SPIRV_CROSS_ENABLE_CPP"] = self.options.cpp
        tc.variables["SPIRV_CROSS_ENABLE_REFLECT"] = self.options.reflect
        tc.variables["SPIRV_CROSS_ENABLE_C_API"] = self.options.c_api
        tc.variables["SPIRV_CROSS_ENABLE_UTIL"] = self.options.util or self.options.build_executable
        tc.variables["SPIRV_CROSS_SKIP_INSTALL"] = False
        tc.variables["SPIRV_CROSS_FORCE_PIC"] = self.options.pic
        tc.variables["SPIRV_CROSS_NAMESPACE_OVERRIDE"] = self.options.namespace
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")
        rm(self, "*.ilk", self.folders.package / "bin")
        rm(self, "*.pdb", self.folders.package / "bin")
        if self.options.shared and self.options.build_executable:
            for static_lib in [
                "spirv-cross-core", "spirv-cross-glsl", "spirv-cross-hlsl", "spirv-cross-msl",
                "spirv-cross-cpp", "spirv-cross-reflect", "spirv-cross-c", "spirv-cross-util",
            ]:
                rm(self, f"*{static_lib}.*", self.folders.package / "lib")

        self._create_cmake_module_alias_targets(
            self.folders.package / self._module_file_rel_path,
            {target: f"spirv-cross::{target}" for target in self._spirv_cross_components.keys()},
        )

    def package_info(self):
        # FIXME: we should provide one CMake config file per target (waiting for an implementation of upstream issue 9000)
        def _register_component(target_lib: str, requires: list[str]):
            self.info.components[target_lib].set_property("cmake_target_name", target_lib)
            if self.options.shared:
                self.info.components[target_lib].set_property("pkg_config_name", target_lib)
            prefix = "d" if self.settings.os == "Windows" and self.settings.build_type == "Debug" else ""
            self.info.components[target_lib].libs = [f"{target_lib}{prefix}"]
            self.info.components[target_lib].includedirs.append(os.path.join("include", "spirv_cross"))
            self.info.components[target_lib].defines.append(f"SPIRV_CROSS_NAMESPACE_OVERRIDE={self.options.namespace}")
            self.info.components[target_lib].requires = requires
            if self.settings.os in ["Linux", "FreeBSD"] and self.options.glsl:
                self.info.components[target_lib].system_libs.append("m")
            if not self.options.shared and self.options.c_api:
                libcxx = stdcpp_library(self)
                if libcxx:
                    self.info.components[target_lib].system_libs.append(libcxx)

        for target_lib, requires in self._spirv_cross_components.items():
            _register_component(target_lib, requires)

    def _create_cmake_module_alias_targets(self, module_file: Path, targets: dict[str, str]):
        content = ""
        for alias, aliased in targets.items():
            content += textwrap.dedent(
                f"""
                if(TARGET {aliased} AND NOT TARGET {alias})
                    add_library({alias} INTERFACE IMPORTED)
                    set_property(TARGET {alias} PROPERTY INTERFACE_LINK_LIBRARIES {aliased})
                endif()
                """)
        save(self, module_file, content)

    @property
    def _module_file_rel_path(self):
        return os.path.join("lib", "cmake", f"recipe-official-{self.name}-targets.cmake")

    @property
    def _spirv_cross_components(self) -> dict[str, list[str]]:
        components: dict[str, list[str]] = {}
        if self.options.shared:
            components.update({"spirv-cross-c-shared": []})
        else:
            components.update({"spirv-cross-core": []})
            if self.options.glsl:
                components.update({"spirv-cross-glsl": ["spirv-cross-core"]})
                if self.options.hlsl:
                    components.update({"spirv-cross-hlsl": ["spirv-cross-glsl"]})
                if self.options.msl:
                    components.update({"spirv-cross-msl": ["spirv-cross-glsl"]})
                if self.options.cpp:
                    components.update({"spirv-cross-cpp": ["spirv-cross-glsl"]})
                if self.options.reflect:
                    components.update({"spirv-cross-reflect": []})
            if self.options.c_api:
                c_api_requires: list[str] = []
                if self.options.glsl:
                    c_api_requires.append("spirv-cross-glsl")
                    if self.options.hlsl:
                        c_api_requires.append("spirv-cross-hlsl")
                    if self.options.msl:
                        c_api_requires.append("spirv-cross-msl")
                    if self.options.cpp:
                        c_api_requires.append("spirv-cross-cpp")
                    if self.options.reflect:
                        c_api_requires.append("spirv-cross-reflect")
                components.update({"spirv-cross-c": c_api_requires})
            if self.options.util:
                components.update({"spirv-cross-util": ["spirv-cross-core"]})
        return components
