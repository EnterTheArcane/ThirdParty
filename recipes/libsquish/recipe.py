from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import apply_patches, copy, get
from thirdparty.scm import SourceForgeProject, Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True
    openmp: bool = False
    sse2_intrinsics: bool = False
    altivec_intrinsics: bool = False


class Recipe(RecipeBase[_Options]):
    name = "libsquish"
    version = "1.15"
    license = "MIT"

    def latest_version(self):
        project = SourceForgeProject(self, "libsquish")
        return Version(project.latest_release(r"libsquish-([\d.]+)\.tgz"))

    def configure(self):
        if self.settings.arch not in self._sse2_compliant_archs:
            self.options.sse2_intrinsics = False
        if self.settings.arch not in self._altivec_compliant_archs:
            self.options.altivec_intrinsics = False

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url=f"https://sourceforge.net/projects/libsquish/files/libsquish-{self.version}.tgz",
            sha256="628796eeba608866183a61d080d46967c9dda6723bc0a3ec52324c85d2147269",
            destination=self.folders.source)
        apply_patches(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["BUILD_SQUISH_WITH_OPENMP"] = self.options.openmp
        tc.variables["BUILD_SQUISH_WITH_SSE2"] = self.options.sse2_intrinsics or False
        tc.variables["BUILD_SQUISH_WITH_ALTIVEC"] = self.options.altivec_intrinsics or False
        tc.variables["BUILD_SQUISH_EXTRA"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.libs = ["squishd" if self.settings.build_type == "Debug" else "squish"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs.append("m")

    @property
    def _sse2_compliant_archs(self):
        return ["X64"]

    @property
    def _altivec_compliant_archs(self):
        return ["ppc32be", "ppc32", "ppc64le", "ppc64"]
