from thirdparty import RecipeBase
from thirdparty.files import get, copy
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "safeint"
    version = "3.24"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "dcleblanc/SafeInt")
        return Version(repo.latest_release)

    def source(self):
        get(
            self,
            url=f"https://github.com/dcleblanc/SafeInt/archive/{self.version}.tar.gz",
            sha256="af6c7222a8420f6f87e198dc94791c28da75fe7241b605342c333fd03fd9dea6",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "SafeInt.hpp", src=self.folders.source, dst=self.folders.package / "include")

    def package_info(self):
        self.info.set_property("cmake_file_name", "safeint")
        self.info.set_property("cmake_target_name", "safeint::safeint")
        self.info.bindirs = []
        self.info.libdirs = []
