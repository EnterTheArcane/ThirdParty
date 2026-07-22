from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeDeps, CMakeToolchain, set_cmake_minimum_required
from thirdparty.files import apply_patches, copy, get, rmdir
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "vorbis"
    version = "1.3.7"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "xiph/vorbis")
        return Version(repo.latest_release.removeprefix("v"))

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")
        self.requires("ogg")

    def source(self):
        get(
            self,
            url=f"https://github.com/xiph/vorbis/archive/v{self.version}.tar.gz",
            sha256="270c76933d0934e42c5ee0a54a36280e2d87af1de3cc3e584806357e237afd13",
            destination=self.folders.source,
            strip_root=True)
        set_cmake_minimum_required(self)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        # Relocatable shared lib on Macos
        tc.cache_variables["CMAKE_POLICY_DEFAULT_CMP0042"] = "NEW"
        tc.generate()
        deps = CMakeDeps(self)
        deps.generate()

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
        self.info.set_property("cmake_file_name", "Vorbis")
        # see https://github.com/recipe-io/recipe-center-index/pull/4173
        self.info.set_property("pkg_config_name", "vorbis-all-do-not-use")

        # vorbis
        self.info.components["vorbismain"].set_property("cmake_target_name", "Vorbis::vorbis")
        self.info.components["vorbismain"].set_property("pkg_config_name", "vorbis")
        self.info.components["vorbismain"].libs = ["vorbis"]
        if self.settings.os in ["Linux", "FreeBSD", "Android"]:
            self.info.components["vorbismain"].system_libs.append("m")
        if self.settings.os == "Android":
            self.info.components["vorbismain"].system_libs.append("log")
        self.info.components["vorbismain"].requires = ["ogg::ogg"]

        # TODO: Upstream VorbisConfig.cmake defines components 'Enc' and 'File',
        # which are related to imported targets Vorbis::vorbisenc and Vorbis::vorbisfile
        # Find a way to emulate this in CMakeDeps. See upstream issue 10258

        # vorbisenc
        self.info.components["vorbisenc"].set_property("cmake_target_name", "Vorbis::vorbisenc")
        self.info.components["vorbisenc"].set_property("pkg_config_name", "vorbisenc")
        self.info.components["vorbisenc"].libs = ["vorbisenc"]
        self.info.components["vorbisenc"].requires = ["vorbismain"]

        # vorbisfile
        self.info.components["vorbisfile"].set_property("cmake_target_name", "Vorbis::vorbisfile")
        self.info.components["vorbisfile"].set_property("pkg_config_name", "vorbisfile")
        self.info.components["vorbisfile"].libs = ["vorbisfile"]
        self.info.components["vorbisfile"].requires = ["vorbismain"]

        # vorbisenc-alias
        self.info.components["vorbisenc-alias"].requires.append("vorbisenc")
        self.info.components["vorbisfile-alias"].requires.append("vorbisfile")
