from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain
from thirdparty.files import apply_patches, copy, get
from thirdparty.microsoft import is_msvc
from thirdparty.scm import SourceForgeProject, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    utils: bool = True


class Recipe(RecipeBase[_Options]):
    name = "giflib"
    version = "6.1.3"
    license = "MIT"

    def latest_version(self):
        project = SourceForgeProject(self, "giflib")
        return Version(project.latest_release(r"giflib-([\d.]+)\.tar\.gz"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")
        if is_msvc(self) and self.options.utils:
            self.requires("getopt-for-visual-studio")

    def source(self):
        get(
            self,
            url=f"https://downloads.sourceforge.net/project/giflib/giflib-6.x/giflib-{self.version}.tar.gz",
            sha256="b65b66b99f0424b93525f987386f22fc5efb9da2bfc92ad4a532249aaffbab0e",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["GIFLIB_SRC_DIR"] = self.folders.source.as_posix()
        tc.variables["UTILS"] = self.options.utils
        tc.generate()

        if is_msvc(self):
            deps = CMakeDeps(self)
            deps.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.recipe)
        cmake.build()

    def package(self):
        copy(self, "COPYING", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.set_property("cmake_file_name", "GIF")
        self.info.set_property("cmake_target_name", "GIF::GIF")
        self.info.libs = ["gif"]
        if is_msvc(self):
            self.info.defines.append("USE_GIF_DLL" if self.options.shared else "USE_GIF_LIB")
