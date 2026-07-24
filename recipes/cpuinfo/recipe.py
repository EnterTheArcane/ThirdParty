from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, replace_in_file, rmdir
from thirdparty.microsoft import is_msvc
from thirdparty.scm import GithubRepository, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "cpuinfo"
    version = "20260723"
    license = "BSD-2-Clause"

    def latest_version(self):
        return Version(GithubRepository(self, "pytorch/cpuinfo").latest_commit_date())

    def configure(self):
        if is_msvc(self):
            # Only static for msvc
            # Injecting CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS is not sufficient since there are global symbols
            self.options.shared = False
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url="https://github.com/pytorch/cpuinfo/archive/d6108819d1d41c749b076e250be454c4559cb771.tar.gz",
            sha256="f02b97e81049d7a0c46c349521a1b16c908abefe0ec7a411dcfbc970afb2a10d",
            destination=self.folders.source,
            strip_root=True)
        replace_in_file(
            self,
            self.folders.source / "CMakeLists.txt",
            "LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}",
            "LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR} RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}")

    def generate(self):
        tc = CMakeToolchain(self)
        # cpuinfo
        tc.cache_variables["CPUINFO_LIBRARY_TYPE"] = "default"
        tc.cache_variables["CPUINFO_RUNTIME_TYPE"] = "default"
        tc.cache_variables["CPUINFO_LOG_LEVEL"] = "default"
        tc.variables["CPUINFO_BUILD_TOOLS"] = False
        tc.variables["CPUINFO_BUILD_UNIT_TESTS"] = False
        tc.variables["CPUINFO_BUILD_MOCK_TESTS"] = False
        tc.variables["CPUINFO_BUILD_BENCHMARKS"] = False
        # clog (always static)
        tc.cache_variables["CLOG_RUNTIME_TYPE"] = "default"
        tc.variables["CLOG_BUILD_TESTS"] = False
        tc.variables["CMAKE_POSITION_INDEPENDENT_CODE"] = self.options.pic
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.set_property("cmake_file_name", "cpuinfo")
        self.info.set_property("pkg_config_name", "libcpuinfo")

        self.info.components["cpuinfo"].set_property("cmake_target_name", "cpuinfo::cpuinfo")
        self.info.components["cpuinfo"].libs = ["cpuinfo"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["cpuinfo"].system_libs.append("pthread")

        if self.settings.os == "Android":
            self.info.components["cpuinfo"].system_libs.append("log")
