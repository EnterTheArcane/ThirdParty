import os

from thirdparty import RecipeBase
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "eigen"
    version = "5.0.1"
    license = "MPL-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "eigen-mirror/eigen")
        return Version(repo.latest_release)

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://gitlab.com/libeigen/eigen/-/archive/{self.version}/eigen-{self.version}.tar.bz2",
            sha256="e4de6b08f33fd8b8985d2f204381408c660bffa6170ac65b68ae1bd3cd575c0a",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        skip_test = self.conf.tools.build.skip_test if self.conf.tools.build.skip_test is not None else True
        tc.cache_variables["BUILD_TESTING"] = not skip_test
        tc.cache_variables["EIGEN_BUILD_BLAS"] = False
        tc.cache_variables["EIGEN_BUILD_LAPACK"] = False
        tc.cache_variables["EIGEN_BUILD_DEMOS"] = False
        tc.cache_variables["EIGEN_BUILD_DOC"] = False
        tc.cache_variables["EIGEN_BUILD_PKGCONFIG"] = False
        tc.cache_variables["EIGEN_BUILD_TESTING"] = tc.cache_variables["BUILD_TESTING"]
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()

        copy(self, "COPYING.*", self.folders.source, self.folders.package / "licenses")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "Eigen3")
        self.info.set_property("cmake_target_name", "Eigen3::Eigen")
        self.info.set_property("pkg_config_name", "eigen3")
        self.info.components["eigen3"].bindirs = []
        self.info.components["eigen3"].libdirs = []
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["eigen3"].system_libs = ["m"]

        self.info.components["eigen3"].set_property("cmake_target_name", "Eigen3::Eigen")
        self.info.components["eigen3"].includedirs = [os.path.join("include", "eigen3")]
