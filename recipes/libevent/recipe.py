from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain, set_cmake_minimum_required
from thirdparty.files import apply_patches, copy, get, replace_in_file, rmdir
from thirdparty.microsoft import is_msvc, is_msvc_static_runtime
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    with_openssl: bool = True
    disable_threads: bool = False


class Recipe(RecipeBase[_Options]):
    name = "libevent"
    version = "2.1.13"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "libevent/libevent")
        return Version(repo.latest_tag_matching(r"release-(\d+(?:\.\d+)+)-stable"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")
        if self.options.with_openssl:
            self.requires("openssl")

    def source(self):
        get(
            self,
            url=f"https://github.com/libevent/libevent/archive/release-{self.version}-stable.tar.gz",
            sha256="1a0885e17dc78afbaeddf13cf849f9238bbc24acdc178464a0d1934d7c5ffbd5",
            destination=self.folders.source,
            strip_root=True)
        set_cmake_minimum_required(self)
        apply_patches(self)
        replace_in_file(
            self,
            self.folders.source / "cmake" / "AddEventLibrary.cmake",
            "INSTALL_NAME_DIR \"${CMAKE_INSTALL_PREFIX}/lib\"",
            "")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["EVENT__LIBRARY_TYPE"] = "SHARED" if self.options.shared else "STATIC"
        tc.variables["EVENT__DISABLE_DEBUG_MODE"] = self.settings.build_type == "Release"
        tc.variables["EVENT__DISABLE_OPENSSL"] = not self.options.with_openssl
        tc.variables["EVENT__DISABLE_THREAD_SUPPORT"] = self.options.disable_threads
        tc.variables["EVENT__DISABLE_BENCHMARK"] = True
        tc.variables["EVENT__DISABLE_TESTS"] = True
        tc.variables["EVENT__DISABLE_REGRESS"] = True
        tc.variables["EVENT__DISABLE_SAMPLES"] = True
        if is_msvc(self):
            tc.variables["EVENT__MSVC_STATIC_RUNTIME"] = is_msvc_static_runtime(self)
        tc.cache_variables["CMAKE_POLICY_VERSION_MINIMUM"] = "3.5"
        tc.generate()
        CMakeDeps(self).generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        CMake(self).install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "Libevent")
        self.info.set_property("pkg_config_name", "libevent")

        self.info.components["core"].set_property("cmake_target_name", "libevent::core")
        self.info.components["core"].set_property("pkg_config_name", "libevent_core")
        self.info.components["core"].libs = ["event_core"]
        if self.settings.os in ["Linux", "FreeBSD"] and not self.options.disable_threads:
            self.info.components["core"].system_libs = ["pthread"]
        if self.settings.os == "Windows":
            self.info.components["core"].system_libs = ["ws2_32", "advapi32", "iphlpapi"]

        self.info.components["extra"].set_property("cmake_target_name", "libevent::extra")
        self.info.components["extra"].set_property("pkg_config_name", "libevent_extra")
        self.info.components["extra"].libs = ["event_extra"]
        self.info.components["extra"].requires = ["core"]
        if self.settings.os == "Windows":
            self.info.components["extra"].system_libs = ["shell32"]

        if self.options.with_openssl:
            self.info.components["openssl"].set_property("cmake_target_name", "libevent::openssl")
            self.info.components["openssl"].set_property("pkg_config_name", "libevent_openssl")
            self.info.components["openssl"].libs = ["event_openssl"]
            self.info.components["openssl"].requires = ["core", "openssl::ssl"]

        if self.settings.os != "Windows" and not self.options.disable_threads:
            self.info.components["pthreads"].set_property("cmake_target_name", "libevent::pthreads")
            self.info.components["pthreads"].set_property("pkg_config_name", "libevent_pthreads")
            self.info.components["pthreads"].libs = ["event_pthreads"]
            self.info.components["pthreads"].requires = ["core"]
