from typing import Literal

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import get, copy, rmdir, apply_patches, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    usingz: Literal["ON", "OFF", "ONLY"] = "ON"
    with_max_precision: int = 8
    with_hi_precision: bool = False


class Recipe(RecipeBase[_Options]):
    name = "clipper2"
    version = "2.0.1"
    license = "BSL-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "AngusJohnson/Clipper2")
        return Version(repo.latest_release.removeprefix("Clipper2_"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/AngusJohnson/Clipper2/archive/refs/tags/Clipper2_{self.version}.tar.gz",
            sha256="2a3693aceab4aed3e39b743e038d87701acc53cf05ed7b2013aab3e0aec5287e",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)
        replace_in_file(self, self.folders.source / "CPP" / "CMakeLists.txt", "-Werror", "")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS"] = True
        tc.variables["CLIPPER2_UTILS"] = False
        tc.variables["CLIPPER2_EXAMPLES"] = False
        tc.variables["CLIPPER2_TESTS"] = False
        tc.variables["CLIPPER2_USINGZ"] = self.options.usingz
        tc.variables["CLIPPER2_HI_PRECISION"] = self.options.with_hi_precision
        tc.variables["CLIPPER2_MAX_PRECISION"] = self.options.with_max_precision
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.source / "CPP")
        cmake.build()

    def package(self):
        copy(self, pattern="LICENSE", dst=self.folders.package / "licenses", src=self.folders.source)
        cmake = CMake(self)
        cmake.install()

        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        if self.options.usingz != "ONLY":
            self.info.components["clipper2"].set_property("cmake_target_name", "Clipper2::clipper2")
            self.info.components["clipper2"].set_property("pkg_config_name", "Clipper2")
            self.info.components["clipper2"].libs = ["Clipper2"]
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.components["clipper2"].system_libs.append("m")

        if self.options.usingz != "OFF":
            self.info.components["clipper2z"].set_property("cmake_target_name", "Clipper2::clipper2z")
            self.info.components["clipper2z"].set_property("pkg_config_name", "Clipper2Z")
            self.info.components["clipper2z"].libs = ["Clipper2Z"]
            self.info.components["clipper2z"].defines.append("USINGZ")
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.components["clipper2z"].system_libs.append("m")
