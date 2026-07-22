from thirdparty import RecipeBase
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "robin-map"
    version = "1.4.1"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "Tessil/robin-map")
        return Version(repo.latest_release.removeprefix("v"))

    def source(self):
        get(
            self,
            url=f"https://github.com/Tessil/robin-map/archive/v{self.version}.tar.gz",
            sha256="0e3f53a377fdcdc5f9fed7a4c0d4f99e82bbb64175233bd13427fef9a771f4a1",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "*.h", src=self.folders.source / "include", dst=self.folders.package / "include")

    def package_info(self):
        self.info.set_property("cmake_file_name", "Robinmap")
        self.info.set_property("cmake_target_name", "tsl::robin_map")
        self.info.set_property("cmake_target_aliases", ["robin-map::robin-map"])
        self.info.bindirs = []
        self.info.libdirs = []
