from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import fix_apple_shared_install_name
from thirdparty.cmake import CMake, CMakeToolchain, CMakeDeps
from thirdparty.files import get, copy, rmdir, replace_in_file
from thirdparty.microsoft import is_msvc, is_msvc_static_runtime
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


# abseil components onnx/onnx_proto link against (mirrors onnx cmake protobuf_ABSL_USED_TARGETS).
_ABSL_DEPS = [
    "absl_absl_check", "absl_absl_log", "absl_algorithm", "absl_base",
    "absl_bind_front", "absl_bits", "absl_btree", "absl_cleanup", "absl_cord",
    "absl_core_headers", "absl_debugging", "absl_die_if_null",
    "absl_dynamic_annotations", "absl_flags", "absl_flat_hash_map",
    "absl_flat_hash_set", "absl_function_ref", "absl_hash", "absl_layout",
    "absl_log_initialize", "absl_log_severity", "absl_memory",
    "absl_node_hash_map", "absl_node_hash_set", "absl_optional", "absl_span",
    "absl_status", "absl_statusor", "absl_strings", "absl_synchronization",
    "absl_time", "absl_type_traits", "absl_utility", "absl_variant",
]


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    disable_static_registration: bool = True


class Recipe(RecipeBase[_Options]):
    name = "onnx"
    version = "1.22.0"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "onnx/onnx")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        if is_msvc(self):
            # Shared onnx on MSVC has link issues; force static.
            self.options.shared = False

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("protobuf")
        self.requires_tool("protobuf")  # protoc at build time
        self.requires("abseil")

    def source(self):
        get(
            self,
            url=f"https://github.com/onnx/onnx/archive/refs/tags/v{self.version}.tar.gz",
            sha256="70bb8b25cf31ea9b1d9f94baacfdc8c4fa27a760f9a10f5d93881bc9eede5fbc",
            destination=self.folders.source,
            strip_root=True)

        # Use conan-provided abseil (CONFIG) and treat protobuf's utf8_range as optional
        # (it is a private static component only exposed for static protobuf builds).
        cmakelists = self.folders.source / "CMakeLists.txt"
        replace_in_file(
            self,
            cmakelists,
            "          find_package(absl REQUIRED)",
            "          find_package(absl REQUIRED CONFIG)")
        replace_in_file(
            self,
            cmakelists,
            "          find_package(utf8_range)",
            "          # find_package(utf8_range)")
        replace_in_file(
            self,
            cmakelists,
            "            absl::variant\n"
            "            utf8_range::utf8_range\n"
            "            utf8_range::utf8_validity\n"
            "          )",
            "            absl::variant\n"
            "          )\n"
            "          if (TARGET utf8_range::utf8_range)\n"
            "            list(APPEND protobuf_ABSL_USED_TARGETS utf8_range::utf8_range utf8_range::utf8_validity)\n"
            "          endif()")

    def generate(self):
        protobuf = self.dependencies["protobuf"].options
        tc = CMakeToolchain(self)
        tc.cache_variables["ONNX_USE_PROTOBUF_SHARED_LIBS"] = bool(protobuf.shared)
        tc.cache_variables["BUILD_SHARED_LIBS"] = self.options.shared
        tc.cache_variables["ONNX_BUILD_PYTHON"] = False
        tc.cache_variables["ONNX_GEN_PB_TYPE_STUBS"] = False
        tc.cache_variables["ONNX_WERROR"] = False
        tc.cache_variables["ONNX_COVERAGE"] = False
        tc.cache_variables["ONNX_BUILD_TESTS"] = False
        tc.cache_variables["ONNX_USE_LITE_PROTO"] = bool(protobuf.lite)
        tc.cache_variables["ONNX_ML"] = True
        tc.cache_variables["ONNX_VERIFY_PROTO3"] = False
        if is_msvc(self):
            tc.cache_variables["ONNX_USE_MSVC_STATIC_RUNTIME"] = is_msvc_static_runtime(self)
        tc.cache_variables["ONNX_DISABLE_STATIC_REGISTRATION"] = self.options.disable_static_registration
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
        rmdir(self, self.folders.package / "lib" / "cmake")
        fix_apple_shared_install_name(self)

    def package_info(self):
        self.info.set_property("cmake_file_name", "ONNX")

        requires = ["protobuf::libprotobuf"] + [f"abseil::{c}" for c in _ABSL_DEPS]
        protobuf = self.dependencies["protobuf"]
        if "utf8_range" in protobuf.info.components:
            requires += ["protobuf::utf8_range", "protobuf::utf8_validity"]

        defines = ["ONNX_NAMESPACE=onnx", "ONNX_ML=1"]
        if self.options.disable_static_registration:
            defines.append("__ONNX_DISABLE_STATIC_REGISTRATION")
        if protobuf.options.lite:
            defines.append("ONNX_USE_LITE_PROTO=1")

        self.info.components["libonnx"].set_property("cmake_target_name", "ONNX::onnx")
        self.info.components["libonnx"].set_property("cmake_target_aliases", ["onnx"])
        self.info.components["libonnx"].libs = ["onnx"]
        self.info.components["libonnx"].defines = defines
        self.info.components["libonnx"].requires = requires

        self.info.components["onnx_proto"].set_property("cmake_target_name", "ONNX::onnx_proto")
        self.info.components["onnx_proto"].set_property("cmake_target_aliases", ["onnx_proto"])
        self.info.components["onnx_proto"].libs = ["onnx_proto"]
        self.info.components["onnx_proto"].defines = defines
        self.info.components["onnx_proto"].requires = requires
