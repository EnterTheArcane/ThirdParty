from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import valid_min_cppstd
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, replace_in_file, rm, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    with_opengl: bool = False
    with_omp: bool = False
    with_cuda: bool = False
    with_clew: bool = False
    with_opencl: bool = False
    with_dx: bool = False
    with_metal: bool = True


class Recipe(RecipeBase[_Options]):
    name = "opensubdiv"
    version = "3.7.0"
    license = "LicenseRef-LICENSE.txt"

    def latest_version(self):
        repo = GithubRepository(self, "PixarAnimationStudios/OpenSubdiv")
        return Version(repo.latest_release.removeprefix("v").replace("_", "."))

    def configure(self):
        if self.settings.os != "Windows":
            self.options.with_dx = False
        if self.settings.os != "Mac":
            self.options.with_metal = False
        self.license = "DocumentRef-LICENSE.txt:LicenseRef-Tomorrow-Open-Source-Technology"

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("onetbb")
        if self.options.with_opengl:
            self.requires("opengl")
            self.requires("glfw")
        if self.options.with_metal:
            self.requires("metal-cpp")

    def source(self):
        get(
            self,
            url="https://github.com/PixarAnimationStudios/OpenSubdiv/archive/refs/tags/v3_7_0.tar.gz",
            sha256="f843eb49daf20264007d807cbc64516a1fed9cdb1149aaf84ff47691d97491f9",
            destination=self.folders.source,
            strip_root=True)
        # opensubdiv adds /W3 to OSD_COMPILER_FLAGS; drop it so the quiet -w wins without D9025.
        replace_in_file(
            self, self.folders.source / "CMakeLists.txt",
            "/W3     # Use warning level recommended for production purposes.",
            "# (W3 removed for quiet -w)", strict=False)

    def generate(self):
        tc = CMakeToolchain(self)
        if not valid_min_cppstd(self, self._min_cppstd):
            tc.variables["CMAKE_CXX_STANDARD"] = self._min_cppstd
        tc.variables["NO_TBB"] = False
        tc.variables["NO_OPENGL"] = not self.options.with_opengl
        tc.variables["BUILD_SHARED_LIBS"] = self.options.shared
        tc.variables["NO_OMP"] = not self.options.with_omp
        tc.variables["NO_CUDA"] = not self.options.with_cuda
        tc.variables["NO_DX"] = not self.options.with_dx
        tc.variables["NO_METAL"] = not self.options.with_metal
        tc.variables["NO_CLEW"] = not self.options.with_clew
        tc.variables["NO_OPENCL"] = not self.options.with_opencl
        tc.variables["NO_PTEX"] = True  # Note: PTEX is for examples only, but we skip them..
        tc.variables["NO_DOC"] = True
        tc.variables["NO_EXAMPLES"] = True
        tc.variables["NO_TUTORIALS"] = True
        tc.variables["NO_REGRESSION"] = True
        tc.variables["NO_TESTS"] = True
        tc.variables["NO_GLTESTS"] = True
        tc.variables["NO_MACOS_FRAMEWORK"] = True
        tc.generate()

        deps = CMakeDeps(self)
        deps.generate()

    def build(self):
        self._patch_sources()
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        if self.options.shared:
            rm(self, "*.a", self.folders.package / "lib")

    def package_info(self):
        self.info.set_property("cmake_file_name", "OpenSubdiv")
        target_suffix = "" if self.options.shared else "_static"

        self.info.components["osdcpu"].set_property("cmake_target_name", f"OpenSubdiv::osdcpu{target_suffix}")
        self.info.components["osdcpu"].libs = ["osdCPU"]
        self.info.components["osdcpu"].requires = ["onetbb::onetbb"]

        if self._osd_gpu_enabled:
            self.info.components["osdgpu"].set_property("cmake_target_name", f"OpenSubdiv::osdgpu{target_suffix}")
            self.info.components["osdgpu"].libs = ["osdGPU"]
            self.info.components["osdgpu"].requires = ["osdcpu"]
            if self.options.with_opengl:
                self.info.components["osdgpu"].requires.extend(["opengl::opengl", "glfw::glfw"])
            if self.options.with_metal:
                self.info.components["osdgpu"].requires.append("metal-cpp::metal-cpp")
            dl_required = self.options.with_opengl or self.options.with_opencl
            if self.settings.os in ["Linux", "FreeBSD"] and dl_required:
                self.info.components["osdgpu"].system_libs = ["dl"]

    @property
    def _min_cppstd(self):
        if self.options.with_metal:
            return "14"
        return "11"

    @property
    def _osd_gpu_enabled(self):
        return any(
            [
                self.options.with_opengl,
                self.options.with_opencl,
                self.options.with_cuda,
                self.options.with_dx,
                self.options.with_metal,
            ])

    def _patch_sources(self):
        apply_patches(self)
        if self.settings.os == "Mac" and not self._osd_gpu_enabled:
            path = self.folders.source / "opensubdiv" / "CMakeLists.txt"
            replace_in_file(self, path, "$<TARGET_OBJECTS:osd_gpu_obj>", "")
        # No warnings as errors
        replace_in_file(self, self.folders.source / "CMakeLists.txt", "/WX", "", strict=False)
