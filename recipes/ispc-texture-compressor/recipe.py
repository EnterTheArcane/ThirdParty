from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get
from thirdparty.scm import GithubRepository, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "ispc-texture-compressor"
    version = "2024.09.23"
    license = "MIT"

    def latest_version(self):
        date = GithubRepository(self, "GameTechDev/ISPCTextureCompressor").latest_commit_date()
        return Version(f"{date[:4]}.{date[4:6]}.{date[6:]}")

    def requirements(self):
        self.requires_tool("cmake")
        self.requires_tool("ispc")

    def source(self):
        get(
            self,
            url="https://github.com/GameTechDev/ISPCTextureCompressor/archive/79ddbc90334fc31edd438e68ccb0fe99b4e15aab.tar.gz",
            sha256="506650f63f7a4a41237206083c8b3785a64daa94d4a896b3757d39581972f70b",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["ISPC_TEXCOMP_SRC_DIR"] = self.folders.source.as_posix()
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.recipe)
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.set_property("cmake_file_name", "ispc-texture-compressor")
        self.info.set_property("cmake_target_name", "ispc_texcomp::ispc_texcomp")
        self.info.libs = ["ispc_texcomp"]
        if self.settings.os == "Windows":
            bin_dir = self.folders.package / "bin"
            self.info.buildenv.prepend_path("PATH", bin_dir)
