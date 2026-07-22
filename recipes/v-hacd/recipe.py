from thirdparty import RecipeBase
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "v-hacd"
    version = "4.1.0"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "kmammou/v-hacd")
        return Version(repo.latest_release.removeprefix("v"))

    def source(self):
        get(
            self,
            url=f"https://github.com/kmammou/v-hacd/archive/refs/tags/v{self.version}.tar.gz",
            sha256="9fe895cd10ec995d2171b11bde97aaaa221b418a3aaed0f5d9a068ae057d626b",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "*.h", src=self.folders.source / "include", dst=self.folders.package / "include")

    def package_info(self):
        self.info.bindirs = []
        self.info.libdirs = []
