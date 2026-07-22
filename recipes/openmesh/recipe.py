from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, rm, rmdir
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version, WebReleaseIndex


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "openmesh"
    version = "11.0"
    license = "BSD-3-Clause"

    def latest_version(self):
        url = "https://www.graphics.rwth-aachen.de/software/openmesh/download/"
        index = WebReleaseIndex(self, url)
        return Version(index.latest_release(r"latest version is OpenMesh (\d+(?:\.\d+)*)"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://www.graphics.rwth-aachen.de/media/openmesh_static/Releases/11.0/OpenMesh-11.0.0.tar.bz2",
            sha256="9d22e65bdd6a125ac2043350a019ec4346ea83922cafdf47e125a03c16f6fa07",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        if self.settings.os == "Windows":
            tc.variables["OPENMESH_BUILD_SHARED"] = self.options.shared
        tc.variables["BUILD_APPS"] = False
        tc.variables["OPENMESH_DOCS"] = False
        tc.variables["CMAKE_CXX_STANDARD"] = 11
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "libdata")
        rmdir(self, self.folders.package / "share")
        if self.settings.os != "Windows":
            if self.options.shared:
                rm(self, "*.a", self.folders.package / "lib")
            else:
                rm(self, "*.so*", self.folders.package / "lib")
                rm(self, "*.dylib", self.folders.package / "lib")

    def package_info(self):
        self.info.set_property("cmake_file_name", "OpenMesh")

        suffix = "d" if self.settings.build_type == "Debug" else ""

        self.info.components["openmeshcore"].set_property("cmake_target_name", "OpenMesh::OpenMeshCore")
        self.info.components["openmeshcore"].libs = ["OpenMeshCore" + suffix]
        if not self.options.shared:
            self.info.components["openmeshcore"].defines.append("OM_STATIC_BUILD")
        if is_msvc(self):
            self.info.components["openmeshcore"].defines.append("_USE_MATH_DEFINES")

        self.info.components["openmeshtools"].set_property("cmake_target_name", "OpenMesh::OpenMeshTools")
        self.info.components["openmeshtools"].libs = ["OpenMeshTools" + suffix]
        self.info.components["openmeshtools"].requires = ["openmeshcore"]
