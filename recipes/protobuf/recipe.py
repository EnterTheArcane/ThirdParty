from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, CMakeDeps
from thirdparty.files import get, copy, rmdir, rm, replace_in_file
from thirdparty.microsoft import is_msvc, is_msvc_static_runtime
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


# abseil components libprotobuf/libprotoc link against.
# Reference: protobuf/cmake/abseil-cpp.cmake for C++ runtime 7.35.1 / release v35.1.
_ABSL_DEPS = [
    "absl_absl_check", "absl_absl_log", "absl_algorithm", "absl_base",
    "absl_bind_front", "absl_bits", "absl_btree", "absl_cleanup", "absl_cord",
    "absl_core_headers", "absl_debugging", "absl_die_if_null",
    "absl_dynamic_annotations", "absl_flags", "absl_flat_hash_map",
    "absl_flat_hash_set", "absl_function_ref", "absl_hash", "absl_layout",
    "absl_log_initialize", "absl_log_globals", "absl_log_severity",
    "absl_memory", "absl_node_hash_map", "absl_node_hash_set", "absl_optional",
    "absl_random_distributions", "absl_random_random", "absl_span",
    "absl_status", "absl_statusor", "absl_strings", "absl_synchronization",
    "absl_time", "absl_utility",
]


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    with_zlib: bool = True
    with_rtti: bool = True
    lite: bool = False


class Recipe(RecipeBase[_Options]):
    name = "protobuf"
    # Protobuf release v35.1 corresponds to C++ runtime 7.35.1.
    version = "7.35.1"
    license = "BSD-3-Clause"

    _cmake_install_base_path = "lib/cmake/protobuf"

    def latest_version(self):
        repo = GithubRepository(self, "protocolbuffers/protobuf")
        release = repo.latest_release.removeprefix("v")
        return Version(f"7.{release}")

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("abseil")
        if self.options.with_zlib:
            self.requires("zlib")

    def source(self):
        get(
            self,
            url="https://github.com/protocolbuffers/protobuf/releases/download/v35.1/protobuf-35.1.tar.gz",
            sha256="f0b6838e7522a8da96126d487068c959bc624926368f3024ac8fd03abd0a1ac4",
            destination=self.folders.source,
            strip_root=True)
        copy(self, "protobuf-conan-protoc-target.cmake", src=self.folders.recipe, dst=self.folders.source)
        # Disable the legacy FindProtobuf logic in protobuf-module.cmake that hard-requires
        # Protobuf_PROTOC_EXECUTABLE at find_package() time. protoc is provided on PATH (via the
        # protobuf tool-require) and as the protobuf::protoc target (protobuf-conan-protoc-target.cmake).
        module_in = self.folders.source / "cmake" / "protobuf-module.cmake.in"
        replace_in_file(self, module_in,
                        "if(DEFINED Protobuf_SRC_ROOT_FOLDER)",
                        "if(0)\nif(DEFINED Protobuf_SRC_ROOT_FOLDER)")
        replace_in_file(self, module_in,
                        "# Define upper case versions of output variables",
                        "endif()")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["protobuf_LOCAL_DEPENDENCIES_ONLY"] = True
        tc.cache_variables["CMAKE_INSTALL_CMAKEDIR"] = self._cmake_install_base_path
        tc.cache_variables["protobuf_WITH_ZLIB"] = self.options.with_zlib
        tc.cache_variables["protobuf_BUILD_TESTS"] = False
        tc.cache_variables["protobuf_BUILD_CONFORMANCE"] = False
        tc.cache_variables["protobuf_BUILD_EXAMPLES"] = False
        tc.cache_variables["protobuf_BUILD_SHARED_LIBS"] = self.options.shared
        tc.cache_variables["protobuf_BUILD_PROTOC_BINARIES"] = True
        tc.cache_variables["protobuf_BUILD_LIBPROTOC"] = True
        tc.cache_variables["protobuf_BUILD_LIBUPB"] = True
        tc.cache_variables["protobuf_DISABLE_RTTI"] = not self.options.with_rtti
        if is_msvc(self) and self.settings.compiler_runtime:
            tc.cache_variables["protobuf_MSVC_STATIC_RUNTIME"] = is_msvc_static_runtime(self)
        tc.generate()

        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake" / "utf8_range")

        cmake_config_folder = self.folders.package / self._cmake_install_base_path
        rm(self, "protobuf-config*.cmake", folder=cmake_config_folder)
        rm(self, "protobuf-targets*.cmake", folder=cmake_config_folder)
        copy(self, "protobuf-conan-protoc-target.cmake", src=self.folders.source, dst=cmake_config_folder)

        if not self.options.lite:
            rm(self, "libprotobuf-lite*", folder=self.folders.package / "lib")
            rm(self, "libprotobuf-lite*", folder=self.folders.package / "bin")

    def package_info(self):
        self.info.set_property("cmake_file_name", "protobuf")
        # onnxruntime does find_package(Protobuf CONFIG); register both casings so both
        # protobuf_DIR and Protobuf_DIR are emitted (consumers resolve by exact-case <name>_DIR).
        self.info.set_property("cmake_file_name_variants", ["protobuf", "Protobuf"])
        self.info.set_property("pkg_config_name", "protobuf_full_package")

        build_modules = [
            f"{self._cmake_install_base_path}/protobuf-generate.cmake",
            f"{self._cmake_install_base_path}/protobuf-module.cmake",
            f"{self._cmake_install_base_path}/protobuf-options.cmake",
            f"{self._cmake_install_base_path}/protobuf-conan-protoc-target.cmake",
        ]
        self.info.set_property("cmake_build_modules", build_modules)

        lib_prefix = "lib" if is_msvc(self) else ""
        lib_suffix = "d" if self.settings.build_type == "Debug" else ""
        absl_deps = [f"abseil::{c}" for c in _ABSL_DEPS]

        if not self.options.shared:
            # utf8 libraries are private and always static; only exposed for static protobuf.
            self.info.components["utf8_range"].set_property("cmake_target_name", "utf8_range::utf8_range")
            self.info.components["utf8_validity"].set_property("cmake_target_name", "utf8_range::utf8_validity")
            if self.settings.os == "Windows":
                self.info.components["utf8_range"].libs = ["libutf8_range"]
                self.info.components["utf8_validity"].libs = ["libutf8_validity"]
            else:
                self.info.components["utf8_range"].libs = ["utf8_range"]
                self.info.components["utf8_validity"].libs = ["utf8_validity"]
            self.info.components["utf8_validity"].requires = ["abseil::absl_strings"]

        # libprotobuf
        self.info.components["libprotobuf"].set_property("cmake_target_name", "protobuf::libprotobuf")
        self.info.components["libprotobuf"].set_property("pkg_config_name", "protobuf")
        self.info.components["libprotobuf"].builddirs.append(self._cmake_install_base_path)
        self.info.components["libprotobuf"].libs = [lib_prefix + "protobuf" + lib_suffix]
        if self.options.with_zlib:
            self.info.components["libprotobuf"].requires = ["zlib::zlib"]
        self.info.components["libprotobuf"].requires.extend(absl_deps)
        if not self.options.shared:
            self.info.components["libprotobuf"].requires.append("utf8_validity")
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["libprotobuf"].system_libs.extend(["m", "pthread"])
        if self.settings.os == "Android":
            self.info.components["libprotobuf"].system_libs.append("log")
        if self.settings.os == "Windows" and self.options.shared:
            self.info.components["libprotobuf"].defines = ["PROTOBUF_USE_DLLS"]

        # libprotoc
        self.info.components["libprotoc"].set_property("cmake_target_name", "protobuf::libprotoc")
        self.info.components["libprotoc"].libs = [lib_prefix + "protoc" + lib_suffix]
        self.info.components["libprotoc"].requires = ["libprotobuf"]
        self.info.components["libprotoc"].requires.extend(absl_deps)
