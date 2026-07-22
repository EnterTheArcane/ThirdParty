from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, rm, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    target: Literal["draco", "encode_and_decode", "encode_only", "decode_only"] = "draco"
    enable_point_cloud_compression: bool = True
    enable_mesh_compression: bool = True
    enable_standard_edgebreaker: bool = True
    enable_predictive_edgebreaker: bool = True


class Recipe(RecipeBase[_Options]):
    name = "draco"
    version = "1.5.7"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "google/draco")
        return Version(repo.latest_release)

    def configure(self):
        if not self.options.enable_mesh_compression:
            self.options.enable_standard_edgebreaker = False
            self.options.enable_predictive_edgebreaker = False

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/google/draco/archive/refs/tags/{self.version}.tar.gz",
            sha256="bf6b105b79223eab2b86795363dfe5e5356050006a96521477973aba8f036fe1",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)

        tc.variables["DRACO_POINT_CLOUD_COMPRESSION"] = self.options.enable_point_cloud_compression
        tc.variables["DRACO_MESH_COMPRESSION"] = self.options.enable_mesh_compression
        if self.options.enable_mesh_compression:
            tc.variables["DRACO_STANDARD_EDGEBREAKER"] = self.options.enable_standard_edgebreaker
            tc.variables["DRACO_PREDICTIVE_EDGEBREAKER"] = self.options.enable_predictive_edgebreaker
        tc.variables["DRACO_ANIMATION_ENCODING"] = False
        tc.variables["DRACO_BACKWARDS_COMPATIBILITY"] = True
        tc.variables["DRACO_DECODER_ATTRIBUTE_DEDUPLICATION"] = False
        tc.variables["DRACO_FAST"] = False
        tc.variables["DRACO_GLTF"] = False
        tc.variables["DRACO_JS_GLUE"] = False
        tc.variables["DRACO_MAYA_PLUGIN"] = False
        tc.variables["DRACO_TESTS"] = False
        tc.variables["DRACO_UNITY_PLUGIN"] = False
        tc.variables["DRACO_WASM"] = False

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
        if self.options.shared:
            rm(self, "*draco.a", self.folders.package / "lib")

    def package_info(self):
        self.info.set_property("cmake_file_name", "draco")
        self.info.set_property("cmake_target_name", "draco::draco")
        self.info.set_property("pkg_config_name", "draco")
        self.info.libs = ["draco"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("m")
