import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, collect_libs, copy, get, replace_in_file, rmdir, rm
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "zstd"
    version = "1.5.7"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "facebook/zstd")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/facebook/zstd/releases/download/v{self.version}/zstd-{self.version}.tar.gz",
            sha256="eb33e51f49a15e023950cd7825ca74a4a2b43db8354825ac24fc1b7ee09e6fa3",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)
        replace_in_file(
            self,
            self.folders.source / "build" / "cmake" / "lib" / "CMakeLists.txt",
            "POSITION_INDEPENDENT_CODE On",
            "")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["ZSTD_BUILD_PROGRAMS"] = True
        tc.variables["ZSTD_BUILD_STATIC"] = True
        tc.variables["ZSTD_BUILD_SHARED"] = self.options.shared
        tc.variables["ZSTD_MULTITHREAD_SUPPORT"] = True
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.source / "build" / "cmake")
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

        if self.options.shared:
            # If we build programs we have to build static libs (see logic in generate()),
            # but if shared is True, we only want shared lib in package folder.
            rm(self, "*_static.*", self.folders.package / "lib")
            for lib in (self.folders.package / "lib").glob("*.a"):
                if not str(lib).endswith(".dll.a"):
                    os.remove(lib)

    def package_info(self):
        zstd_cmake = "libzstd_shared" if self.options.shared else "libzstd_static"
        self.info.set_property("cmake_file_name", "zstd")
        self.info.set_property("cmake_target_name", f"zstd::{zstd_cmake}")
        self.info.set_property("pkg_config_name", "libzstd")
        self.info.set_property("cmake_target_aliases", ["zstd::libzstd"])
        self.info.components["zstdlib"].libs = collect_libs(self)
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["zstdlib"].system_libs.append("pthread")
