from thirdparty import RecipeBase, RecipeOptions
from thirdparty.cmake import CMake, CMakeToolchain
from thirdparty.files import get, save
from thirdparty.scm import Version


class _Options(RecipeOptions):
    shared: bool = False
    pic: bool = True


class Recipe(RecipeBase[_Options]):
    name = "mikktspace"
    version = "2020.03.25"
    license = "Zlib"

    def latest_version(self):
        return Version(self.version)

    def configure(self):
        self.settings.compiler_cxx_standard = None
        self.settings.compiler_libcxx = None

    def requirements(self):
        self.requires_tool("cmake")

    def source(self):
        get(
            self,
            url="https://github.com/mmikk/MikkTSpace/archive/3e895b49d05ea07e4c2133156cfa94369e19e409.tar.gz",
            sha256="aeba65ddee85a679133d510d71d00b108f603752f90b15b9ecf7777033f6e351",
            destination=self.folders.source,
            strip_root=True)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["MIKKTSPACE_SRC_DIR"] = self.folders.source.as_posix()
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure(build_script_folder=self.folders.recipe)
        cmake.build()

    def package(self):
        save(self, self.folders.package / "licenses" / "LICENSE", self._extracted_license)
        cmake = CMake(self)
        cmake.install()

    def package_info(self):
        self.info.libs = ["mikktspace"]
        if not self.options.shared and self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs = ["m"]

    @property
    def _extracted_license(self):
        with open(self.folders.source / "mikktspace.h") as f:
            lines = f.readlines()
        return "".join(line[4:] for line in lines[4:21])
