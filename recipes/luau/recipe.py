from thirdparty import RecipeBase
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import get, copy
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "luau"
    version = "0.730"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "luau-lang/luau")
        return Version(repo.latest_release)

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/luau-lang/luau/archive/{self.version}.tar.gz",
            sha256="448d720df65d393f4c61c7d2b2ddde8c772de55c23760603a9ada43a752aef70",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["LUAU_BUILD_CLI"] = False
        tc.variables["LUAU_BUILD_TESTS"] = False
        tc.variables["LUAU_BUILD_WEB"] = False
        tc.variables["LUAU_WERROR"] = False
        tc.variables["LUAU_STATIC_CRT"] = False
        tc.variables["LUAU_BUILD_SHARED"] = False
        tc.variables["LUAU_EXTERN_C"] = False
        tc.variables["LUAU_SRC_DIR"] = self.folders.source.as_posix()
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.recipe)
        cmake.build()

    def package(self):
        copy(self, "lua_LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.set_property("cmake_file_name", "Luau")
        self.info.set_property("cmake_target_name", "Luau::Luau")
        # Common
        self.info.components["Common"].libs = ["Luau.Common"]
        self.info.components["Common"].set_property("cmake_target_name", "Luau::Common")
        # Ast
        self.info.components["Ast"].libs = ["Luau.Ast"]
        self.info.components["Ast"].set_property("cmake_target_name", "Luau::Ast")
        self.info.components["Ast"].requires = ["Common"]
        # VM
        self.info.components["VM"].libs = ["Luau.VM"]
        self.info.components["VM"].set_property("cmake_target_name", "Luau::VM")
        self.info.components["VM"].requires = ["Common"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["VM"].system_libs = ["m"]
        # Analysis
        self.info.components["Analysis"].libs = ["Luau.Analysis"]
        self.info.components["Analysis"].set_property("cmake_target_name", "Luau::Analysis")
        self.info.components["Analysis"].requires = ["Ast", "Config", "Compiler", "VM"]
        # Config
        self.info.components["Config"].libs = ["Luau.Config"]
        self.info.components["Config"].set_property("cmake_target_name", "Luau::Config")
        self.info.components["Config"].requires = ["Ast", "Compiler", "VM"]
        # Compiler
        self.info.components["Compiler"].libs = ["Luau.Compiler"]
        self.info.components["Compiler"].set_property("cmake_target_name", "Luau::Compiler")
        self.info.components["Compiler"].requires = ["Ast"]
        # CodeGen
        self.info.components["CodeGen"].libs = ["Luau.CodeGen"]
        self.info.components["CodeGen"].set_property("cmake_target_name", "Luau::CodeGen")
        self.info.components["CodeGen"].requires = ["VM", "Common"]
        # Require
        self.info.components["Require"].libs = ["Luau.Require"]
        self.info.components["Require"].set_property("cmake_target_name", "Luau::Require")
        self.info.components["Require"].requires = ["Config", "VM"]
        # Web
        if self.options.with_web:
            self.info.components["Web"].libs = ["Luau.Web"]
            self.info.components["Web"].set_property("cmake_target_name", "Luau::Web")
            self.info.components["Web"].requires = ["Compiler", "VM", "Analysis"]
