from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain, set_cmake_minimum_required
from thirdparty.files import apply_patches, copy, get, replace_in_file, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "openddl-parser"
    version = "0.5.2"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "kimkulling/openddl-parser")
        return Version(repo.latest_release.removeprefix("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/kimkulling/openddl-parser/archive/v{self.version}.tar.gz",
            sha256="8058caacdc989a010c2ad3ab62df99f9f3034b4981649c5fb832efa6fbf10c36",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)
        # Strip the project's unconditional /W4 so the quiet -w wins without cl's D9025 spam
        # (set(CMAKE_CXX_FLAGS) can't be intercepted by the toolchain's compile_options override).
        replace_in_file(
            self,
            self.folders.source / "CMakeLists.txt",
            "${CMAKE_CXX_FLAGS} /W4",
            "${CMAKE_CXX_FLAGS}",
            strict=False)
        set_cmake_minimum_required(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["DDL_STATIC_LIBRARY"] = not self.options.shared
        tc.variables["DDL_BUILD_TESTS"] = False
        tc.variables["DDL_BUILD_PARSER_DEMO"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "lib" / "cmake")

    def package_info(self):
        self.info.set_property("cmake_file_name", "openddlparser")
        self.info.set_property("cmake_target_name", "openddlparser::openddlparser")
        self.info.libs = ["openddlparser"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("m")
        if not self.options.shared:
            self.info.defines.append("OPENDDL_STATIC_LIBARY")
