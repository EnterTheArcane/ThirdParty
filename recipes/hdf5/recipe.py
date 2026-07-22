import os

from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, replace_in_file, rm, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    enable_cxx: bool = True
    hl: bool = True


class Recipe(RecipeBase[_Options]):
    name = "hdf5"
    version = "2.1.1"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "HDFGroup/hdf5")
        return Version(repo.latest_release)

    def configure(self):
        if not self.options.enable_cxx:
            self.settings.compiler_cxx_standard = None
            self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("zlib")

    def source(self):
        get(
            self,
            url=f"https://github.com/HDFGroup/hdf5/archive/refs/tags/{self.version}.tar.gz",
            sha256="5849ed7a81be6bc84ff8aa65dd966430adf0daf71e6bcb734b7a37474f92c859",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)
        # hdf5 appends /W3 to HDF5_CMAKE_C[XX]_FLAGS (applied via variables the toolchain filter
        # can't intercept); drop it (keep the /wd suppressions) so the quiet -w wins without D9025.
        replace_in_file(
            self, self.folders.source / "config" / "flags" / "HDFCompilerCXXFlags.cmake",
            'HDF5_CMAKE_CXX_FLAGS "/W3" "/wd4100"', 'HDF5_CMAKE_CXX_FLAGS "/wd4100"', strict=False)
        replace_in_file(
            self, self.folders.source / "config" / "flags" / "HDFCompilerFlags.cmake",
            'HDF5_CMAKE_C_FLAGS "/W3" "/wd4100"', 'HDF5_CMAKE_C_FLAGS "/wd4100"', strict=False)

    def generate(self):
        deps = CMakeDeps(self)
        deps.generate()

        tc = CMakeToolchain(self)
        tc.variables["BUILD_STATIC_EXECS"] = False
        tc.variables["BUILD_STATIC_LIBS"] = not self.options.shared
        tc.variables["BUILD_TESTING"] = False
        tc.variables["HDF5_ALLOW_UNSUPPORTED"] = False
        tc.variables["HDF5_BUILD_CPP_LIB"] = self.options.enable_cxx
        tc.variables["HDF5_BUILD_EXAMPLES"] = False
        tc.variables["HDF5_BUILD_FORTRAN"] = False
        tc.variables["HDF5_BUILD_HL_LIB"] = self.options.hl
        tc.variables["HDF5_BUILD_JAVA"] = False
        tc.variables["HDF5_BUILD_TOOLS"] = False
        tc.variables["HDF5_ENABLE_COVERAGE"] = False
        tc.variables["HDF5_ENABLE_DEPRECATED_SYMBOLS"] = True
        tc.variables["HDF5_ENABLE_PARALLEL"] = False
        tc.variables["HDF5_ENABLE_PREADWRITE"] = True
        tc.variables["HDF5_ENABLE_SZIP_SUPPORT"] = False
        tc.variables["HDF5_ENABLE_THREADSAFE"] = False
        tc.variables["HDF5_ENABLE_TRACE"] = False
        tc.variables["HDF5_ENABLE_USING_MEMCHECKER"] = False
        tc.variables["HDF5_ENABLE_ZLIB_SUPPORT"] = True
        tc.variables["HDF5_EXTERNAL_LIB_PREFIX"] = ""
        tc.variables["HDF5_EXTERNALLY_CONFIGURED"] = True
        tc.variables["HDF5_INSTALL_INCLUDE_DIR"] = "include/hdf5"
        tc.variables["HDF5_NO_PACKAGES"] = True
        tc.variables["HDF5_ONLY_SHARED_LIBS"] = self.options.shared
        tc.variables["HDF5_PACKAGE_EXTLIBS"] = False
        tc.variables["HDF5_USE_FOLDERS"] = False
        tc.generate()

    def build(self):
        replace_in_file(
            self,
            self.folders.source / "CMakeLists.txt",
            "set (CMAKE_POSITION_INDEPENDENT_CODE ON)",
            "")
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "pkgconfig")
        rm(self, "libhdf5.settings", self.folders.package / "lib")
        rm(self, "*.pdb", self.folders.package / "bin")
        if self.options.shared:
            for root, _, files in os.walk(self.folders.package / "lib"):
                for f in files:
                    if f.endswith(".a") and not f.endswith(".dll.a"):
                        os.remove(os.path.join(root, f))

    def package_info(self):
        self.info.set_property("cmake_file_name", "HDF5")
        self.info.set_property("cmake_target_name", "HDF5::HDF5")

        def _lib_name(lib: str) -> str:
            if self.settings.os == "Windows" and self.settings.compiler != "gcc" and not self.options.shared:
                lib = "lib" + lib
            if self.settings.build_type == "Debug":
                debug_postfix = "_D" if self.settings.os == "Windows" else "_debug"
                return lib + debug_postfix
            return lib

        self.info.components["hdf5_c"].set_property("cmake_target_name", "HDF5::C")
        self.info.components["hdf5_c"].libs = [_lib_name("hdf5")]
        self.info.components["hdf5_c"].requires = ["zlib::zlib"]
        self.info.components["hdf5_c"].includedirs = ["include", os.path.join("include", "hdf5")]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["hdf5_c"].system_libs.extend(["dl", "m"])
        elif self.settings.os == "Windows":
            self.info.components["hdf5_c"].system_libs.append("Shlwapi")
        if self.options.shared:
            self.info.components["hdf5_c"].defines.append("H5_BUILT_AS_DYNAMIC_LIB")

        if self.options.enable_cxx:
            self.info.components["hdf5_cpp"].set_property("cmake_target_name", "HDF5::CXX")
            self.info.components["hdf5_cpp"].libs = [_lib_name("hdf5_cpp")]
            self.info.components["hdf5_cpp"].requires = ["hdf5_c"]
            self.info.components["hdf5_cpp"].includedirs = ["include", os.path.join("include", "hdf5")]

        if self.options.hl:
            self.info.components["hdf5_hl"].set_property("cmake_target_name", "HDF5::HL")
            self.info.components["hdf5_hl"].libs = [_lib_name("hdf5_hl")]
            self.info.components["hdf5_hl"].requires = ["hdf5_c"]
            self.info.components["hdf5_hl"].includedirs = ["include", os.path.join("include", "hdf5")]
            if self.options.enable_cxx:
                self.info.components["hdf5_hl_cpp"].set_property("cmake_target_name", "HDF5::HL_CXX")
                self.info.components["hdf5_hl_cpp"].libs = [_lib_name("hdf5_hl_cpp")]
                self.info.components["hdf5_hl_cpp"].requires = ["hdf5_c", "hdf5_cpp", "hdf5_hl"]
                self.info.components["hdf5_hl_cpp"].includedirs = ["include", os.path.join("include", "hdf5")]
