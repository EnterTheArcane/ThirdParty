from thirdparty import RecipeBase
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "sse2neon"
    version = "1.9.1"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "DLTcollab/sse2neon")
        return Version(repo.latest_release.removeprefix("v"))

    def source(self):
        get(
            self,
            url=f"https://github.com/DLTcollab/sse2neon/archive/refs/tags/v{self.version}.tar.gz",
            sha256="6b70e7cb8c5ce4641002b85deaafe97efdf9ade9b49884edeaf678b35f0e132f",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "sse2neon.h", src=self.folders.source, dst=self.folders.package / "include")

    def package_info(self):
        self.info.bindirs = []
        self.info.libdirs = []
