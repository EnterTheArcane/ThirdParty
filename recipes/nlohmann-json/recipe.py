from thirdparty import RecipeBase
from thirdparty.files import get, copy
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "nlohmann-json"
    version = "3.12.0"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "nlohmann/json")
        return Version(repo.latest_release.removeprefix("v"))

    def package_id(self):
        return "universal"

    def source(self):
        get(
            self,
            url=f"https://github.com/nlohmann/json/archive/v{self.version}.tar.gz",
            sha256="4b92eb0c06d10683f7447ce9406cb97cd4b453be18d7279320f7b2f025c10187",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE*", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "*", src=self.folders.source / "include", dst=self.folders.package / "include")

    def package_info(self):
        self.info.set_property("cmake_file_name", "nlohmann_json")
        self.info.set_property("cmake_target_name", "nlohmann_json::nlohmann_json")
        self.info.set_property("pkg_config_name", "nlohmann_json")
        self.info.bindirs = []
        self.info.libdirs = []
