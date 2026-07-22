import shutil

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import cross_building
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import copy, get, replace_in_file, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = True
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "openusd"
    version = "26.08"
    license = "LicenseRef-LICENSE.txt"

    def latest_version(self):
        repo = GithubRepository(self, "PixarAnimationStudios/OpenUSD")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")
        self.requires_tool("cpython")
        self.requires("cpython")
        self.requires("onetbb")

    def source(self):
        get(
            self,
            url=f"https://github.com/PixarAnimationStudios/OpenUSD/archive/refs/tags/v{self.version}.tar.gz",
            sha256="4bccbb95cddda1dbeef2f74a08b9456352f2aa91bfd4578c0c613009c7950149",
            destination=self.folders.source,
            strip_root=True)
        # openusd hardcodes /W3 into _PXR_CXX_FLAGS (which lands in CMAKE_CXX_FLAGS), conflicting
        # with the framework's quiet -w -> "D9025: overriding '/w' with '/W3'" for ~every source
        # file. Drop it so -w wins (verbose builds still get warnings via the compiler default).
        replace_in_file(
            self,
            self.folders.source / "cmake" / "defaults" / "msvcdefaults.cmake",
            'set(_PXR_CXX_FLAGS "${_PXR_CXX_FLAGS} /W3")',
            'set(_PXR_CXX_FLAGS "${_PXR_CXX_FLAGS}")',
            strict=False)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_SHARED_LIBS"] = self.options.shared
        tc.variables["PXR_BUILD_ALEMBIC_PLUGIN"] = False
        tc.variables["PXR_BUILD_DOCUMENTATION"] = False
        tc.variables["PXR_BUILD_DRACO_PLUGIN"] = False
        tc.variables["PXR_BUILD_EMBREE_PLUGIN"] = False
        tc.variables["PXR_BUILD_EXEC"] = True
        tc.variables["PXR_BUILD_EXAMPLES"] = False
        tc.variables["PXR_BUILD_IMAGING"] = False
        tc.variables["PXR_BUILD_MONOLITHIC"] = True
        tc.variables["PXR_BUILD_OPENCOLORIO_PLUGIN"] = False
        tc.variables["PXR_BUILD_OPENIMAGEIO_PLUGIN"] = False
        tc.variables["PXR_BUILD_PRMAN_PLUGIN"] = False
        tc.variables["PXR_BUILD_PYTHON_DOCUMENTATION"] = False
        tc.variables["PXR_BUILD_TESTS"] = False
        tc.variables["PXR_BUILD_TUTORIALS"] = False
        tc.variables["PXR_BUILD_USD_IMAGING"] = False
        tc.variables["PXR_BUILD_USD_TOOLS"] = False
        tc.variables["PXR_BUILD_USD_VALIDATION"] = False
        tc.variables["PXR_BUILD_USDVIEW"] = False
        tc.variables["PXR_ENABLE_GL_SUPPORT"] = False
        tc.variables["PXR_ENABLE_HDF5_SUPPORT"] = False
        tc.variables["PXR_ENABLE_MATERIALX_SUPPORT"] = False
        tc.variables["PXR_ENABLE_METAL_SUPPORT"] = False
        tc.variables["PXR_ENABLE_OPENVDB_SUPPORT"] = False
        tc.variables["PXR_ENABLE_OSL_SUPPORT"] = False
        tc.variables["PXR_ENABLE_PTEX_SUPPORT"] = False
        tc.variables["PXR_ENABLE_PYTHON_SUPPORT"] = True
        tc.variables["PXR_ENABLE_VULKAN_SUPPORT"] = False
        tc.variables["PXR_STRICT_BUILD_MODE"] = False
        tc.variables["PXR_VALIDATE_GENERATED_CODE"] = False

        python_pkg = self.dependencies["cpython"]
        python_root = python_pkg.folders.package
        python_major, python_minor = str(python_pkg.version).split(".")[:2]
        extension = "dylib" if self.settings.os == "Mac" else "so"
        if self.settings.os == "Windows":
            python_executable = python_root / "bin" / "python3.exe"
            python_include = python_root / "bin" / "include"
            python_library = python_root / "bin" / "libs" / "python3.lib"
        else:
            python_executable = python_root / "bin" / "python3"
            # CPython's packaged include layout is platform-specific: the macOS recipe
            # normalizes it to include/python, while Linux retains include/pythonX.Y.
            versioned_include = python_root / "include" / f"python{python_major}.{python_minor}"
            python_include = (versioned_include if versioned_include.is_dir()
                              else python_root / "include" / "python")
            python_library = python_root / "lib" / f"libpython3.{extension}"

        # CMake 4.4's FindPython3 derives the development version from the library
        # filename. The CPython recipe intentionally installs a version-neutral
        # libpython3 name, so provide a private versioned alias for discovery.
        if self.settings.os == "Windows":
            discovery_name = f"python{python_major}{python_minor}.lib"
        else:
            discovery_name = f"libpython{python_major}.{python_minor}.{extension}"
        discovery_library = self.folders.build / discovery_name
        shutil.copy2(python_library, discovery_library)

        tc.variables["Python3_ROOT_DIR"] = python_root.as_posix()
        tc.variables["Python3_FIND_STRATEGY"] = "LOCATION"
        tc.variables["Python3_EXECUTABLE"] = python_executable.as_posix()
        tc.variables["Python3_INCLUDE_DIR"] = python_include.as_posix()
        tc.variables["Python3_LIBRARY"] = discovery_library.as_posix()
        if self.settings.os == "Windows":
            tc.variables["Python3_FIND_REGISTRY"] = "NEVER"

        if cross_building(self):
            # FindPython3 runs the interpreter during configure (and OpenUSD runs it for build-time
            # codegen), but the target aarch64 python can't execute on the build host. Use the
            # build-context (host) interpreter for running, while keeping the target headers/lib so
            # the python bindings still link against the aarch64 libpython.
            host_python_root = self.dependencies.build["cpython"].folders.package
            host_executable = host_python_root / "bin" / (
                "python3.exe" if self.settings.os == "Windows" else "python3")
            tc.variables["Python3_EXECUTABLE"] = host_executable.as_posix()

        tc.generate()

        deps = CMakeDeps(self)
        deps.set_property("onetbb", "cmake_file_name", "TBB")
        deps.set_property("onetbb", "cmake_target_name", "TBB::tbb")
        # Don't generate CMake files for cpython - use FindPython3 directly via Python3_ROOT_DIR.
        # cpython is required in both the host and build (tool) contexts, and the build context
        # must be suppressed too; otherwise CMakeDeps still emits Python3Config.cmake for the
        # tool-context cpython, whose target file calls find_dependency(Curses) for its transitive
        # ncurses - which fails because no CursesConfig.cmake is generated.
        deps.set_property("cpython", "cmake_find_mode", "none")
        deps.set_property("cpython", "cmake_find_mode", "none", build_context=True)
        # Don't generate CMake files for transitive deps that OpenUSD finds via FindPython3
        # ncurses is a transitive dep of cpython
        deps.set_property("ncurses", "cmake_find_mode", "none")
        deps.set_property("ncurses", "cmake_find_mode", "none", build_context=True)
        deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "pxr")
        self.info.set_property("cmake_target_name", "pxr::usd_m")

        self.info.libs = ["usd_ms" if self.options.shared else "usd_m"]
        if not self.options.shared:
            self.info.defines = ["PXR_STATIC=1"]
        if self.settings.os == "Windows":
            self.info.defines = (self.info.defines or []) + ["NOMINMAX"]
        if self.settings.os in ("Linux", "FreeBSD"):
            self.info.system_libs = ["pthread", "dl", "m"]

        self.info.requires = ["onetbb::onetbb"]
        self.info.requires.append("cpython::cpython")
