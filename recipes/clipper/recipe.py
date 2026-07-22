from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, set_cmake_minimum_required
from thirdparty.files import apply_patches, copy, get, rmdir
from thirdparty.scm import SourceForgeProject, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "clipper"
    version = "6.4.2"
    license = "BSL-1.0"

    def latest_version(self):
        project = SourceForgeProject(self, "polyclipping")
        return Version(project.latest_release(r"clipper_ver([\d.]+)\.zip"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://sourceforge.net/projects/polyclipping/files/clipper_ver{self.version}.zip",
            sha256="a14320d82194807c4480ce59c98aa71cd4175a5156645c4e2b3edd330b930627",
            destination=self.folders.source)
        apply_patches(self)
        set_cmake_minimum_required(self, path=self.folders.source / "cpp" / "CMakeLists.txt")

    def generate(self):
        tc = CMakeToolchain(self)
        # Export symbols for msvc shared
        tc.variables["CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS"] = True
        # Relocatable shared lib on Macos
        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0042"] = "NEW"
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.source / "cpp")
        cmake.build()

    def package(self):
        copy(self, "License.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("pkg_config_name", "polyclipping")
        self.info.libs = ["polyclipping"]

        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("m")
