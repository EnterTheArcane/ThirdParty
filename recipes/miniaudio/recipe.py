from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    header_only: bool = True


class Recipe(RecipeBase[_Options]):
    name = "miniaudio"
    version = "0.11.25"
    license = "Unlicense"

    def latest_version(self):
        repo = GithubRepository(self, "mackron/miniaudio")
        return Version(repo.latest_release)

    def configure(self):
        self.settings.compiler_libcxx = None
        self.settings.compiler_cxx_standard = None

    def requirements(self):
        if not self.options.header_only:
            self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://github.com/mackron/miniaudio/archive/{self.version}.tar.gz",
            sha256="b900edcffe979816e2560a0580b9b1216d674b4f17fbadeca8f777a7f8ab0274",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        if self.options.header_only:
            return
        tc = CMakeToolchain(self)
        tc.variables["MINIAUDIO_SRC_DIR"] = self.folders.source.as_posix()
        tc.variables["MINIAUDIO_VERSION_STRING"] = self.version
        tc.generate()

    def build(self):
        if self.options.header_only:
            return
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.recipe)
        cmake.build()

    def package(self):
        copy(self, "LICENSE", dst=self.folders.package / "licenses", src=self.folders.source)
        copy(
            self,
            pattern="**",
            dst=self.folders.package / "include" / "extras",
            src=self.folders.source / "extras",
        )
        if self.options.header_only:
            copy(self, "miniaudio.h", dst=self.folders.package / "include", src=self.folders.source)
            copy(
                self,
                pattern="miniaudio.*",
                dst=self.folders.package / "include" / "extras" / "miniaudio_split",
                src=self.folders.source / "extras" / "miniaudio_split",
            )
        else:
            cmake = CMake(self)
            cmake.install()

    def package_info(self):
        if self.options.header_only:
            self.info.bindirs = []
            self.info.libdirs = []
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.extend(["m", "pthread"])
        if self.settings.os == "Linux":
            self.info.system_libs.append("dl")
        if self.settings.os == "Mac":
            self.info.frameworks.extend(["CoreFoundation", "CoreAudio", "AudioUnit"])
            self.info.defines.append("MA_NO_RUNTIME_LINKING=1")
