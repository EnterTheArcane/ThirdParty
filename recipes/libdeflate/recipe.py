from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import collect_libs, copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libdeflate"
    version = "1.25"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "ebiggers/libdeflate")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/ebiggers/libdeflate/archive/refs/tags/v{self.version}.tar.gz",
            sha256="d11473c1ad4c57d874695e8026865e38b47116bbcb872bfc622ec8f37a86017d",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["LIBDEFLATE_BUILD_STATIC_LIB"] = not self.options.shared
        tc.variables["LIBDEFLATE_BUILD_SHARED_LIB"] = self.options.shared
        tc.variables["LIBDEFLATE_BUILD_GZIP"] = False
        tc.variables["LIBDEFLATE_BUILD_TESTS"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "COPYING", self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "libdeflate")
        target_suffix = "_shared" if self.options.shared else "_static"
        self.info.set_property("cmake_target_name", f"libdeflate::libdeflate{target_suffix}")
        self.info.set_property("cmake_target_aliases", ["libdeflate::libdeflate"])  # not official, avoid to break users
        self.info.set_property("pkg_config_name", "libdeflate")
        self.info.components["_libdeflate"].libs = collect_libs(self)
        if self.settings.os == "Windows" and self.options.shared:
            self.info.components["_libdeflate"].defines.append("LIBDEFLATE_DLL")

        self.info.components["_libdeflate"].set_property("cmake_target_name", f"libdeflate::libdeflate{target_suffix}")
        self.info.components["_libdeflate"].set_property("pkg_config_name", "libdeflate")
