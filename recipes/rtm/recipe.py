from thirdparty import RecipeBase
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "rtm"
    version = "2.3.1"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "nfrechette/rtm")
        return Version(repo.latest_release.lstrip("v"))

    def source(self):
        get(
            self,
            url=f"https://github.com/nfrechette/rtm/archive/v{self.version}.tar.gz",
            sha256="a16fc698feca580533fa12c92fe7d1df4f341f807df7ec314274659fdfec11fb",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(
            self, "*.h", src=self.folders.source / "includes",
            dst=self.folders.package / "include")

    def package_info(self):
        self.info.set_property("cmake_file_name", "rtm")
        self.info.set_property("cmake_target_name", "rtm::rtm")
        self.info.bindirs = []
        self.info.libdirs = []
