from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, rmdir
from thirdparty.microsoft import is_msvc
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    header_only: bool = False
    shared: bool = False
    pic: bool = True
    with_fmt_alias: bool = False
    with_os_api: bool = True


class Recipe(RecipeBase[_Options]):
    name = "fmt"
    version = "12.2.0"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "fmtlib/fmt")
        return Version(repo.latest_release)

    def configure(self):
        if self.options.header_only:
            self.options.with_os_api = False

    def requirements(self):
        if not self.options.header_only:
            self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/fmtlib/fmt/releases/download/{self.version}/fmt-{self.version}.zip",
            sha256="a2f4a8d51178f954e4c339007f77edd76ba0cb2e36f87a48e5a5403d9be5878f",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        if not self.options.header_only:
            tc = CMakeToolchain(self)
            tc.cache_variables["FMT_DOC"] = False
            tc.cache_variables["FMT_TEST"] = False
            tc.cache_variables["FMT_INSTALL"] = True
            tc.cache_variables["FMT_LIB_DIR"] = "lib"
            tc.cache_variables["FMT_OS"] = bool(self.options.with_os_api)
            tc.cache_variables["FMT_UNICODE"] = True
            tc.generate()

    def build(self):
        if not self.options.header_only:
            cmake = CMake(self)
            cmake.configure()
            cmake.build()

    def package(self):
        copy(self, pattern="LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        if self.options.header_only:
            copy(self, pattern="*.h", src=self.folders.source / "include", dst=self.folders.package / "include")
        else:
            cmake = CMake(self)
            cmake.install()
            rmdir(self, self.folders.package / "lib" / "cmake")
            rmdir(self, self.folders.package / "lib" / "pkgconfig")
            rmdir(self, self.folders.package / "res")
            rmdir(self, self.folders.package / "share")

    def package_info(self):
        target = "fmt-header-only" if self.options.header_only else "fmt"
        self.info.set_property("cmake_file_name", "fmt")
        self.info.set_property("cmake_target_name", f"fmt::{target}")

        # Mirror upstream find package version policy:
        # https://github.com/fmtlib/fmt/blob/11.1.1/CMakeLists.txt#L403-L407
        self.info.set_property("cmake_config_version_compat", "AnyNewerVersion")
        self.info.set_property("pkg_config_name", "fmt")

        if is_msvc(self):
            self.info.components["_fmt"].cxxflags.append("/utf-8")

        if self.options.with_fmt_alias:
            self.info.components["_fmt"].defines.append("FMT_STRING_ALIAS=1")

        if self.options.header_only:
            self.info.components["_fmt"].defines.append("FMT_HEADER_ONLY=1")
            self.info.components["_fmt"].libdirs = []
            self.info.components["_fmt"].bindirs = []
        else:
            postfix = "d" if self.settings.build_type == "Debug" else ""
            libname = "fmt" + postfix
            self.info.components["_fmt"].libs = [libname]
            if self.settings.os == "Linux":
                self.info.components["_fmt"].system_libs.extend(["m"])
            if self.options.shared:
                self.info.components["_fmt"].defines.append("FMT_SHARED")

        self.info.components["_fmt"].set_property("cmake_target_name", f"fmt::{target}")
