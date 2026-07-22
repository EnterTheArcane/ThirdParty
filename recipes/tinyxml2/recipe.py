from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "tinyxml2"
    version = "11.0.0"
    license = "Zlib"

    def latest_version(self):
        repo = GithubRepository(self, "leethomason/tinyxml2")
        return Version(repo.latest_release)

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/leethomason/tinyxml2/archive/refs/tags/{self.version}.tar.gz",
            sha256="5556deb5081fb246ee92afae73efd943c889cef0cafea92b0b82422d6a18f289",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_TESTING"] = False
        tc.generate()

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

    def package_info(self):
        self.info.set_property("cmake_file_name", "tinyxml2")
        self.info.set_property("cmake_target_name", "tinyxml2::tinyxml2")
        self.info.set_property("pkg_config_name", "tinyxml2")
        postfix = ""
        self.info.libs = [f"tinyxml2{postfix}"]
        if self.settings.os == "Windows" and self.options.shared:
            self.info.defines.append("TINYXML2_IMPORT")
