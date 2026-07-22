from thirdparty import RecipeBase
from thirdparty.files import get, copy
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "dirent"
    version = "1.26"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "tronkko/dirent")
        return Version(repo.latest_release)

    def source(self):
        get(
            self,
            url=f"https://github.com/tronkko/dirent/archive/{self.version}.tar.gz",
            sha256="a91662ee5243d2dae5aee7ed8527f95097afda517cc5cc7ca2699648a74a419c",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, pattern="LICENSE", dst=self.folders.package / "licenses", src=self.folders.source)
        copy(
            self,
            pattern="*.h",
            dst=self.folders.package / "include",
            src=self.folders.source / "include",
        )

    def package_info(self):
        self.info.bindirs = []
        self.info.libdirs = []
