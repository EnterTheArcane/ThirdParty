from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get, replace_in_file, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    build_gen_msl: bool = True
    with_openimageio: bool = False


class Recipe(RecipeBase[_Options]):
    name = "materialx"
    version = "1.39.5"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "AcademySoftwareFoundation/MaterialX")
        return Version(repo.latest_release.lstrip("v"))

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/AcademySoftwareFoundation/MaterialX/archive/refs/tags/v{self.version}.tar.gz",
            sha256="c0d739b70a36f6f72888a0e8e66db5c83ae87c40737cc9b51c108166804f3a3b",
            destination=self.folders.source,
            strip_root=True)
        replace_in_file(
            self, self.folders.source / "CMakeLists.txt",
            "set(CMAKE_CXX_STANDARD", "# set(CMAKE_CXX_STANDARD")
        replace_in_file(
            self, self.folders.source / "CMakeLists.txt",
            "set(CMAKE_POSITION_INDEPENDENT_CODE", "# set(CMAKE_POSITION_INDEPENDENT_CODE")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["MATERIALX_BUILD_DOCS"] = False
        tc.variables["MATERIALX_BUILD_EDITOR"] = False
        tc.variables["MATERIALX_BUILD_GEN_MSL"] = self.options.build_gen_msl
        tc.variables["MATERIALX_BUILD_RENDER"] = False
        tc.variables["MATERIALX_BUILD_SHARED_LIBS"] = self.options.shared
        tc.variables["MATERIALX_BUILD_TESTS"] = False
        tc.variables["MATERIALX_BUILD_VIEWER"] = False
        tc.variables["MATERIALX_INSTALL_PYTHON"] = False
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
        rmdir(self, self.folders.package / "lib" / "pkgconfig")

    def package_info(self):
        self.info.set_property("cmake_file_name", "MaterialX")

        components = [
            ("MaterialXCore", "MaterialX::MaterialXCore"),
            ("MaterialXFormat", "MaterialX::MaterialXFormat"),
            ("MaterialXGenGlsl", "MaterialX::MaterialXGenGlsl"),
            ("MaterialXGenMdl", "MaterialX::MaterialXGenMdl"),
            ("MaterialXGenOsl", "MaterialX::MaterialXGenOsl"),
            ("MaterialXGenShader", "MaterialX::MaterialXGenShader"),
            ("MaterialXRender", "MaterialX::MaterialXRender"),
            ("MaterialXRenderGlsl", "MaterialX::MaterialXRenderGlsl"),
            ("MaterialXRenderHw", "MaterialX::MaterialXRenderHw"),
            ("MaterialXRenderOsl", "MaterialX::MaterialXRenderOsl"),
        ]
        if self.options.build_gen_msl:
            components.append(("MaterialXGenMsl", "MaterialX::MaterialXGenMsl"))
        if self.settings.os == "Mac":
            components.append(("MaterialXRenderMsl", "MaterialX::MaterialXRenderMsl"))

        for comp_name, target_name in components:
            self.info.components[comp_name].set_property("cmake_target_name", target_name)
            self.info.components[comp_name].libs = [comp_name]

        if self.settings.os == "Windows":
            self.info.components["MaterialXRenderGlsl"].system_libs = ["opengl32"]
        elif self.settings.os in ["Linux", "FreeBSD"]:
            self.info.components["MaterialXRenderGlsl"].system_libs = ["GL"]
