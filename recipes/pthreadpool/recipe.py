from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, CMakeDeps
from thirdparty.files import get, copy, replace_in_file
from thirdparty.scm import GithubRepository, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "pthreadpool"
    version = "20260518"
    license = "BSD-2-Clause"

    def latest_version(self):
        return Version(GithubRepository(self, "google/pthreadpool").latest_commit_date())

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("fxdiv")

    def source(self):
        # Extract into a "src" subfolder so the conan-style wrapper CMakeLists.txt
        # (which injects a bare `fxdiv` target) can `add_subdirectory(src)`.
        get(
            self,
            url="https://github.com/google/pthreadpool/archive/02460584c6092e527c8b89f7df4de143d70e801f.zip",
            sha256="5ab4e8f63e3dcf62048360c216532bdf62f00dc204883a52d91230402f0feb6a",
            destination=self.folders.source / "src",
            strip_root=True)
        copy(self, "CMakeLists.txt", src=self.folders.recipe, dst=self.folders.source)
        replace_in_file(
            self,
            self.folders.source / "src" / "CMakeLists.txt",
            "LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}",
            "LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR} RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["PTHREADPOOL_LIBRARY_TYPE"] = "default"
        tc.variables["PTHREADPOOL_ALLOW_DEPRECATED_API"] = True
        tc.variables["PTHREADPOOL_BUILD_TESTS"] = False
        tc.variables["PTHREADPOOL_BUILD_BENCHMARKS"] = False
        # Avoid the FXdiv download; the wrapper provides the fxdiv target instead.
        tc.cache_variables["FXDIV_SOURCE_DIR"] = "dummy"
        tc.variables["CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS"] = True
        tc.generate()
        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source / "src", dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.set_property("cmake_file_name", "pthreadpool")
        self.info.components["pthreadpool"].set_property("cmake_target_name", "pthreadpool")
        self.info.components["pthreadpool"].libs = ["pthreadpool"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["pthreadpool"].system_libs = ["pthread"]
