import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "sdformat"
    version = "16.1.0"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "gazebosim/sdformat")
        tag = repo.latest_release
        return Version(tag.split("_", 1)[-1])

    def requirements(self):
        self.requires_tool("cmake")
        self.requires_tool("gz-cmake")
        self.requires("gz-cmake")
        self.requires("gz-math")
        self.requires("gz-utils")
        self.requires("tinyxml2")

    def source(self):
        version_major = Version(self.version).major
        get(
            self,
            url=f"https://github.com/gazebosim/sdformat/archive/refs/tags/sdformat{version_major}_{self.version}.tar.gz",
            sha256="f9ef71787b0055f7ee35a3b52f42a9d6397f0c2f21f9572957bc3f456e2ca674",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tinyxml2_pkg = self.dependencies["tinyxml2"].folders.package.as_posix()
        tinyxml2_lib = self.dependencies["tinyxml2"].info.libs[0]

        tc = CMakeToolchain(self)
        tc.variables["BUILD_TESTING"] = False
        tc.variables["SKIP_PYBIND11"] = True
        # Use internal urdf copy to avoid external urdfdom/console-bridge deps
        tc.variables["USE_INTERNAL_URDF"] = True

        # Pre-set TINYXML2 variables so gz-cmake's FindTINYXML2.cmake creates
        # TINYXML2::TINYXML2 target from these without searching
        # (find_path and find_library skip searching when cache vars are already set).
        tc.variables["TINYXML2_INCLUDE_DIRS"] = f"{tinyxml2_pkg}/include"
        if self.settings.os == "Windows":
            tc.variables["TINYXML2_LIBRARIES"] = f"{tinyxml2_pkg}/lib/{tinyxml2_lib}.lib"
        elif self.settings.os == "Mac":
            if self.dependencies["tinyxml2"].options.shared:
                tc.variables["TINYXML2_LIBRARIES"] = f"{tinyxml2_pkg}/lib/lib{tinyxml2_lib}.dylib"
            else:
                tc.variables["TINYXML2_LIBRARIES"] = f"{tinyxml2_pkg}/lib/lib{tinyxml2_lib}.a"
        else:
            if self.dependencies["tinyxml2"].options.shared:
                tc.variables["TINYXML2_LIBRARIES"] = f"{tinyxml2_pkg}/lib/lib{tinyxml2_lib}.so"
            else:
                tc.variables["TINYXML2_LIBRARIES"] = f"{tinyxml2_pkg}/lib/lib{tinyxml2_lib}.a"
        tc.generate()

        deps = CMakeDeps(self)
        deps.set_property("gz-cmake", "cmake_find_mode", "none")
        deps.set_property("gz-math", "cmake_find_mode", "none")
        deps.set_property("gz-utils", "cmake_find_mode", "none")
        # tinyxml2 is found via gz-cmake's FindTINYXML2.cmake using the
        # pre-set TINYXML2_LIBRARIES/TINYXML2_INCLUDE_DIRS variables above
        deps.set_property("tinyxml2", "cmake_find_mode", "none")
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.set_property("cmake_find_mode", "none")

        version_major = self.version.split(".")[0]

        self.info.components["sdformat"].libs = [f"sdformat{version_major}"]
        self.info.components["sdformat"].builddirs = [""]
        self.info.components["sdformat"].set_property("cmake_file_name", "sdformat16")
        self.info.components["sdformat"].set_property("cmake_target_name", "sdformat16::sdformat16")
        self.info.components["sdformat"].includedirs = [os.path.join("include", "sdformat16")]
        self.info.components["sdformat"].requires = [
            "gz-cmake::gz-cmake",
            "gz-math::core",
            "gz-utils::core",
            "tinyxml2::tinyxml2",
        ]
        if self.settings.os in ("Linux", "FreeBSD"):
            self.info.components["sdformat"].system_libs = ["dl"]
