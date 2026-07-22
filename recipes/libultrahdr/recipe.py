from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, CMakeDeps
from thirdparty.files import apply_patches, copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libultrahdr"
    version = "1.4.0"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "google/libultrahdr")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("libjpeg-turbo")

    def source(self):
        get(
            self,
            url=f"https://github.com/google/libultrahdr/archive/refs/tags/v{self.version}.tar.gz",
            sha256="e7e1252e2c44d8ed6b99ee0f67a3caf2d8a61c43834b13b1c3cd485574c03ab9",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)

        # Force-disable fallback to internal dependency builder if no deps found
        tc.cache_variables["UHDR_BUILD_DEPS"] = False
        tc.cache_variables["UHDR_BUILD_EXAMPLES"] = False
        tc.cache_variables["CMAKE_REQUIRE_FIND_PACKAGE_JPEG"] = True

        tc.generate()
        deps = CMakeDeps(self)
        deps.set_property("libjpeg-turbo", "cmake_file_name", "JPEG")
        deps.set_property("libjpeg-turbo", "cmake_target_name", "JPEG::JPEG")
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()

        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.libs = ["uhdr"]
        self.info.requires = ["libjpeg-turbo::jpeg"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs = ["pthread"]
