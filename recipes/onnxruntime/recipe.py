import sys

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.apple import is_apple_os
from thirdparty.cmake import CMake, CMakeToolchain, CMakeDeps
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.microsoft import is_msvc
from thirdparty.files import get, copy, rmdir, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository
from thirdparty.shell import run


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    # XNNPACK EP is wired but OFF by default: onnxruntime 1.24.4 expects the XNNPACK API from its
    # pinned commit 3cf85e705098622d59056dcb8f5f963ea7bb0a00 (2025.06.22), newer than the
    # xnnpack recipe's 20241203. The older xn_create_fully_connected_nc_f32 signature (12 args
    # vs 11) breaks core/providers/xnnpack. Bump the xnnpack recipe to that commit to enable.
    with_xnnpack: bool = False
    # CUDA EP is fully wired (cutlass dep, arch list, provider patch) but OFF by default:
    # it additionally requires a cuDNN install + the cudnn_frontend sources, and a CUDA
    # toolkit whose supported SM archs match CMAKE_CUDA_ARCHITECTURES below. Set to True on a
    # machine with the CUDA toolkit + cuDNN available to build the CUDA execution provider.
    with_cuda: bool = False


class Recipe(RecipeBase[_Options]):
    name = "onnxruntime"
    version = "1.27.1"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "microsoft/onnxruntime")
        return Version(repo.latest_release.removeprefix("v"))
    
    def configure(self):
        self.settings.compiler_cxx_standard = "20"

    def requirements(self):
        self.requires_tool("cmake")
        self.requires_tool("flatbuffers")  # flatc regenerates schemas for the packaged FlatBuffers version
        self.requires_tool("protobuf")  # protoc at build time
        self.requires("abseil")
        self.requires("boost")
        self.requires("cpuinfo")
        self.requires("date")
        self.requires("eigen")
        self.requires("flatbuffers")
        self.requires("ms-gsl")
        self.requires("nlohmann-json")
        self.requires("onnx")
        self.requires("protobuf")
        self.requires("re2")
        self.requires("safeint")
        if self.settings.os != "Windows":
            self.requires("nsync")
        else:
            self.requires("wil")
        if self.options.with_xnnpack:
            self.requires("xnnpack")
            self.requires("pthreadpool")
        if self.options.with_cuda:
            self.requires("cutlass")

    def validate(self):
        onnx = self.dependencies["onnx"].options
        if not onnx.disable_static_registration:
            raise RecipeInvalidConfiguration("onnxruntime requires onnx built with disable_static_registration=True")
        if onnx.get_safe("shared"):
            raise RecipeInvalidConfiguration("onnxruntime requires onnx built static (onnx:shared=False)")

    def source(self):
        get(
            self,
            url=f"https://github.com/microsoft/onnxruntime/archive/refs/tags/v{self.version}.tar.gz",
            sha256="e53b06ccd454f56088fde374d1af6660ef111ca7ce7a98d62b274ff9094d3005",
            destination=self.folders.source,
            strip_root=True)
        # Replace onnxruntime's FetchContent dependency logic with find_package(... CONFIG).
        copy(self, "onnxruntime_external_deps.cmake",
             src=self.folders.recipe / "cmake",
             dst=self.folders.source / "cmake" / "external")
        # Don't try to derive the version from git.
        replace_in_file(self, self.folders.source / "cmake" / "CMakeLists.txt",
                        "if (Git_FOUND)", "if (FALSE)")
        # onnxruntime forces /W4 on its own code via set_msvc_c_cpp_compiler_warning_level(4),
        # which builds "/W${warning_level}" and applies it as a genex directory COMPILE_OPTIONS
        # entry (invisible to a literal /W4 search and preserved past the toolchain warning filter).
        # It overrides the quiet -w -> "D9025: overriding '/w' with '/W4'" for ~every source file
        # AND re-enables thousands of C4100/C4267/... warnings. Make the constructed flag empty so
        # no /W level is set and -w wins.
        replace_in_file(
            self, self.folders.source / "cmake" / "CMakeLists.txt",
            'set(warning_flag "/W${warning_level}")', 'set(warning_flag "")', strict=False)
        # Drop /sdl: it promotes C4996 to a hard error, and the vendored abseil (20260526)
        # marks absl::disjunction/conjunction/negation deprecated (protobuf still uses them).
        replace_in_file(
            self,
            self.folders.source / "cmake" / "CMakeLists.txt",
            '      target_compile_options(${target_name} PRIVATE '
            '"$<$<COMPILE_LANGUAGE:CUDA>:SHELL:--compiler-options /sdl>" '
            '"$<$<COMPILE_LANGUAGE:CXX,C>:/sdl>")',
            '')

    def generate(self):
        protobuf = self.dependencies["protobuf"].options
        tc = CMakeToolchain(self)
        # Disable downloading dependencies to ensure the vendored ones are used.
        tc.cache_variables["FETCHCONTENT_FULLY_DISCONNECTED"] = True
        tc.cache_variables["onnxruntime_BUILD_SHARED_LIB"] = self.options.shared
        tc.cache_variables["onnxruntime_USE_FULL_PROTOBUF"] = not protobuf.lite
        tc.cache_variables["onnxruntime_USE_XNNPACK"] = self.options.with_xnnpack
        tc.cache_variables["onnxruntime_USE_CUDA"] = self.options.with_cuda
        if self.options.with_cuda:
            # CUDA 13+ dropped older SM archs (sm_60/sm_70) that onnxruntime requests by default.
            # Restrict to architectures supported by modern CUDA toolkits (Turing..Hopper).
            tc.cache_variables["CMAKE_CUDA_ARCHITECTURES"] = "75-real;80-real;86-real;89-real;90a-real"
        tc.cache_variables["onnxruntime_BUILD_UNIT_TESTS"] = False
        tc.cache_variables["onnxruntime_DISABLE_CONTRIB_OPS"] = False
        tc.cache_variables["onnxruntime_USE_FLASH_ATTENTION"] = False
        tc.cache_variables["onnxruntime_DISABLE_RTTI"] = False
        tc.cache_variables["onnxruntime_DISABLE_EXCEPTIONS"] = False
        tc.cache_variables["onnxruntime_ARMNN_RELU_USE_CPU"] = False
        tc.cache_variables["onnxruntime_ARMNN_BN_USE_CPU"] = False
        tc.cache_variables["onnxruntime_ENABLE_CPU_FP16_OPS"] = False
        tc.cache_variables["onnxruntime_ENABLE_EAGER_MODE"] = False
        tc.cache_variables["onnxruntime_ENABLE_LAZY_TENSOR"] = False
        tc.cache_variables["onnxruntime_ENABLE_CUDA_EP_INTERNAL_TESTS"] = False
        tc.cache_variables["onnxruntime_USE_NEURAL_SPEED"] = False
        tc.cache_variables["onnxruntime_USE_MEMORY_EFFICIENT_ATTENTION"] = False
        # Disable a warning that gets converted to an error.
        tc.preprocessor_definitions["_SILENCE_ALL_CXX23_DEPRECATION_WARNINGS"] = "1"
        # The vendored abseil (20260526) marks absl::disjunction/conjunction/negation deprecated
        # (they are aliases of the std traits); protobuf still uses them, and onnxruntime compiles
        # with /WX, turning the deprecation (C4996) into an error. Suppress that specific warning.
        if is_msvc(self):
            tc.extra_cxxflags.append("/wd4996")
        else:
            tc.extra_cxxflags.append("-Wno-deprecated-declarations")
        tc.generate()

        deps = CMakeDeps(self)
        deps.set_property("flatbuffers", "cmake_target_name", "flatbuffers::flatbuffers")
        deps.generate()

    def build(self):
        flatc_name = "flatc.exe" if self.settings.os == "Windows" else "flatc"
        flatc = self.dependencies.build["flatbuffers"].folders.package / "bin" / flatc_name
        schema_scripts = [
            self.folders.source / "onnxruntime" / "core" / "flatbuffers" / "schema" / "compile_schema.py",
            self.folders.source / "onnxruntime" / "lora" / "adapter_format" / "compile_schema.py",
        ]
        for script in schema_scripts:
            run(self, f'"{sys.executable}" "{script}" --flatc "{flatc}" --language cpp')

        cmake = CMake(self)
        cmake.configure(
            build_script_folder=self.folders.source / "cmake",
            cli_args=["--compile-no-warning-as-error"])
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        if self.options.shared:
            self.info.libs = ["onnxruntime"]
        else:
            # Order matters:
            # https://github.com/microsoft/onnxruntime/blob/v1.23.2/cmake/onnxruntime.cmake#L240
            onnxruntime_libs = [
                "session",
                *(["providers_xnnpack"] if self.options.with_xnnpack else []),
                "optimizer",
                "providers",
                "lora",
                "framework",
                "graph",
                "util",
                "mlas",
                "common",
                "flatbuffers",
            ]
            self.info.libs = [f"onnxruntime_{lib}" for lib in onnxruntime_libs]

        self.info.includedirs.append("include/onnxruntime")
        if not self.options.shared:
            self.info.includedirs.append("include/onnxruntime/core/session")

        if self.settings.os in ["Linux", "Android", "FreeBSD", "SunOS", "AIX"]:
            self.info.system_libs.append("m")
        if self.settings.os in ["Linux", "FreeBSD", "SunOS", "AIX"]:
            self.info.system_libs.append("pthread")
        if is_apple_os(self):
            self.info.frameworks.append("Foundation")
        if self.settings.os == "Windows":
            self.info.system_libs.append("shlwapi")

        self.info.set_property("cmake_file_name", "onnxruntime")
        self.info.set_property("cmake_target_name", "onnxruntime::onnxruntime")
        self.info.set_property("pkg_config_name", "onnxruntime")
