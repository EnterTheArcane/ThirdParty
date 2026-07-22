from thirdparty import RecipeBase
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "fast-float"
    version = "8.2.10"
    license = "Apache-2.0", "BSL-1.0", "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "fastfloat/fast_float")
        return Version(repo.latest_release.removeprefix("v"))

    def source(self):
        get(
            self,
            url=f"https://github.com/fastfloat/fast_float/archive/refs/tags/v{self.version}.tar.gz",
            sha256="76f958dd97b1cf4d8862d1f0986a47d4bdfa8845252bae15ef0f40de3b95961f",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "*", src=self.folders.source / "include", dst=self.folders.package / "include")

    def package_info(self):
        self.info.set_property("cmake_file_name", "FastFloat")
        self.info.set_property("cmake_target_name", "FastFloat::fast_float")
        self.info.bindirs = []
        self.info.libdirs = []

        self.info.components["fastfloat"].set_property("cmake_target_name", "FastFloat::fast_float")
        self.info.components["fastfloat"].bindirs = []
        self.info.components["fastfloat"].libdirs = []
