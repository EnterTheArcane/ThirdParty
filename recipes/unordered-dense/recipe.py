from thirdparty import RecipeBase
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "unordered-dense"
    version = "4.8.1"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "martinus/unordered_dense")
        return Version(repo.latest_release.removeprefix("v"))

    def source(self):
        get(
            self,
            url=f"https://github.com/martinus/unordered_dense/archive/v{self.version}.tar.gz",
            sha256="9f7202ec6d8353932ef865d33f5872e4b7a1356e9032da7cd09c3a0c5bb2b7de",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(
            self, "*.h", src=self.folders.source / "include" / "ankerl",
            dst=self.folders.package / "include" / "ankerl")

    def package_info(self):
        self.info.set_property("cmake_file_name", "unordered_dense")
        self.info.set_property("cmake_target_name", "unordered_dense::unordered_dense")
        self.info.bindirs = []
        self.info.libdirs = []
