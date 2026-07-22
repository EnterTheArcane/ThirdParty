from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, replace_in_file, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "kuba-zip"
    version = "0.3.14"
    license = "Unlicense"

    def latest_version(self):
        repo = GithubRepository(self, "kuba--/zip")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/kuba--/zip/archive/v{self.version}.tar.gz",
            sha256="72d05d00de7bb2f0811d237b30d16de42f1e1dfbb2c33fb41191e3cf27fc7958",
            destination=self.folders.source,
            strip_root=True)
        replace_in_file(self, self.folders.source / "CMakeLists.txt", "-Werror", "")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["CMAKE_DISABLE_TESTING"] = True
        tc.variables["ZIP_STATIC_PIC"] = self.options.pic
        tc.variables["ZIP_BUILD_DOCS"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "UNLICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "zip")
        self.info.set_property("cmake_target_name", "zip::zip")

        self.info.libs = ["zip"]
        if self.options.shared:
            self.info.defines.append("ZIP_SHARED")
