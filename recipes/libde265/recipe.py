from thirdparty import RecipeBase, RecipeOptions
from thirdparty.build import stdcpp_library
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get, replace_in_file, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    sse: bool = True


class Recipe(RecipeBase[_Options]):
    name = "libde265"
    version = "1.1.1"
    license = "LGPL-3.0-or-later"

    def latest_version(self):
        repo = GithubRepository(self, "strukturag/libde265")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        if self.settings.arch not in ["X64"]:
            self.options.sse = False

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/strukturag/libde265/releases/download/v{self.version}/libde265-{self.version}.tar.gz",
            sha256="fd48a927e94ed74fc7ce8829d222b9d8599fcbfe8b6448ba66705babc56ab219",
            destination=self.folders.source,
            strip_root=True)
        self._patch_sources()

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["CMAKE_POSITION_INDEPENDENT_CODE"] = self.options.pic
        tc.variables["ENABLE_SDL"] = False
        tc.variables["DISABLE_SSE"] = not self.options.sse
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "libde265")
        self.info.set_property("cmake_target_name", "de265")
        self.info.set_property("cmake_target_aliases", ["libde265"])  # official imported target before 1.0.10
        self.info.set_property("pkg_config_name", "libde265")
        prefix = "lib" if self.settings.os == "Windows" and not self.options.shared else ""
        self.info.libs = [f"{prefix}de265"]
        if not self.options.shared:
            self.info.defines = ["LIBDE265_STATIC_BUILD"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs = ["m", "pthread"]
        if not self.options.shared:
            libcxx = stdcpp_library(self)
            if libcxx:
                self.info.system_libs.append(libcxx)

    def _patch_sources(self):
        apply_patches(self)
        replace_in_file(
            self, self.folders.source / "CMakeLists.txt",
            "set(CMAKE_POSITION_INDEPENDENT_CODE ON)", "")
