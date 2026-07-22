from thirdparty import RecipeBase
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "animation-compression-library"
    version = "2.1.0"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "nfrechette/acl")
        return Version(repo.latest_release.lstrip("v"))

    def requirements(self):
        self.requires("rtm")

    def source(self):
        get(
            self,
            url=f"https://github.com/nfrechette/acl/archive/v{self.version}.tar.gz",
            sha256="0ac8473cd30eb768bae1ef58558e3088242d6fef81f727ce7b5ff5af9be74fce",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(
            self, "*.h", src=self.folders.source / "includes",
            dst=self.folders.package / "include")

    def package_info(self):
        self.info.set_property("cmake_file_name", "acl")
        self.info.set_property("cmake_target_name", "acl::acl")
        self.info.bindirs = []
        self.info.libdirs = []
