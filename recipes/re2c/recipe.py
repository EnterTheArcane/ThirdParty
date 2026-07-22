from thirdparty import RecipeBase
from thirdparty.cmake import CMakeToolchain, CMake
from thirdparty.files import copy, get, rmdir, replace_in_file
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "re2c"
    version = "4.5.1"
    license = "LicenseRef-re2c"

    def latest_version(self):
        repo = GithubRepository(self, "skvadrik/re2c")
        return Version(repo.latest_release)

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/skvadrik/re2c/releases/download/{self.version}/re2c-{self.version}.tar.xz",
            sha256="ffea067c11aa668bcb42885be6e6cd000302000b7747d2bb213299ec66b7864e",
            destination=self.folders.source,
            strip_root=True)
        # re2c adds /W3 to CMAKE_CXX_FLAGS via try_cxxflag (which tests its first arg); the tested
        # flag isn't visible to the toolchain's compile_options filter. Drop /W3 so /wd4068 becomes
        # the tested flag (keeping the suppressions) and the quiet -w wins without cl's D9025 spam.
        replace_in_file(
            self, self.folders.source / "cmake" / "Re2cCompilerFlags.cmake",
            'try_cxxflag("/W3"', "try_cxxflag(", strict=False)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["RE2C_REBUILD_DOCS"] = False
        tc.cache_variables["RE2C_BUILD_BENCHMARKS"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(
            self, "LICENSE",
            src=self.folders.source,
            dst=self.folders.package / "licenses",
            keep_path=False)
        copy(
            self, "NO_WARRANTY",
            src=self.folders.source,
            dst=self.folders.package / "licenses",
            keep_path=False)
        copy(
            self, "*.re",
            src=self.folders.source / "include",
            dst=self.folders.package / "include",
            keep_path=False)

        cmake = CMake(self)
        cmake.install()
        rmdir(self, self.folders.package / "share")

    def package_info(self):
        self.info.frameworkdirs = []
        self.info.libdirs = []
        self.info.resdirs = []
        self.info.includedirs = []

        include_dir = self.folders.package / "include"
        self.info.buildenv.define("RE2C_STDLIB_DIR", include_dir.as_posix())
