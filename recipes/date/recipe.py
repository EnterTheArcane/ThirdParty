from thirdparty import RecipeBase
from thirdparty.files import get, copy
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "date"
    version = "3.0.4"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "HowardHinnant/date")
        return Version(repo.latest_release.removeprefix("v"))

    def source(self):
        get(
            self,
            url=f"https://github.com/HowardHinnant/date/archive/refs/tags/v{self.version}.tar.gz",
            sha256="56e05531ee8994124eeb498d0e6a5e1c3b9d4fccbecdf555fe266631368fb55f",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        # Header-only: avoids the tz library (and its libcurl dependency).
        copy(self, "*.h", src=self.folders.source / "include", dst=self.folders.package / "include")

    def package_info(self):
        self.info.set_property("cmake_file_name", "date")
        self.info.set_property("cmake_target_name", "date::date")
        self.info.defines = ["DATE_HEADER_ONLY"]
        self.info.bindirs = []
        self.info.libdirs = []
