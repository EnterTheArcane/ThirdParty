from thirdparty import RecipeBase
from thirdparty.files import apply_patches, copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "robin-hood-hashing"
    version = "3.11.5"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "martinus/robin-hood-hashing")
        return Version(repo.latest_release)

    def source(self):
        get(
            self,
            url=f"https://github.com/martinus/robin-hood-hashing/archive/refs/tags/{self.version}.tar.gz",
            sha256="3693e44dda569e9a8b87ce8263f7477b23af448a3c3600c8ab9004fe79c20ad0",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(
            self, "robin_hood.h", src=self.folders.source / "src" / "include",
            dst=self.folders.package / "include")

    def package_info(self):
        self.info.set_property("cmake_file_name", "robin_hood")
        self.info.set_property("cmake_target_name", "robin_hood::robin_hood")
        self.info.bindirs = []
        self.info.libdirs = []
