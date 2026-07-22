from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, rm, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "c4core"
    version = "0.6.0"
    license = "MIT",

    def latest_version(self):
        repo = GithubRepository(self, "biojppm/c4core")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("fast-float")

    def source(self):
        get(
            self,
            url=f"https://github.com/biojppm/c4core/releases/download/v{self.version}/c4core-{self.version}-src.tgz",
            sha256="fd0a3e2c39a5985c6699e306ead71e8a73a6ada2577c905734a2a6ba0a61c1b7",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["C4CORE_WITH_FASTFLOAT"] = True
        tc.variables["C4CORE_WITH_FASTFLOAT_SYSTEM"] = True
        tc.generate()

        deps = CMakeDeps(self)
        # c4core's system-fast-float path calls find_package(fast_float), while the
        # dependency's public target remains FastFloat::fast_float.
        deps.set_property("fast-float", "cmake_file_name", "fast_float")
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, pattern="LICENSE*", dst=self.folders.package / "licenses", src=self.folders.source)
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "cmake")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rm(self, "*.natvis", self.folders.package / "include", recursive=True)

    def package_info(self):
        self.info.libs = ["c4core"]
        self.info.set_property("cmake_file_name", "c4core")
        self.info.set_property("cmake_target_name", "c4core::c4core")

        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("m")
