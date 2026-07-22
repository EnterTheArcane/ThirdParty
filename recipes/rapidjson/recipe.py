from thirdparty import RecipeBase
from thirdparty.files import apply_patches, get, copy
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository

class Recipe(RecipeBase):
    name = "rapidjson"
    version = "1.1.0"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "Tencent/rapidjson")
        return Version(repo.latest_release.removeprefix("v"))

    def source(self):
        get(
            self,
            url=f"https://github.com/Tencent/rapidjson/archive/v{self.version}.tar.gz",
            sha256="bf7ced29704a1e696fbccf2a2b4ea068e7774fa37f6d7dd4039d0787f8bed98e",
            strip_root=True,
            destination=self.folders.source)
        apply_patches(self)

    def package(self):
        copy(self, pattern="license.txt", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, pattern="*", src=self.folders.source / "include", dst=self.folders.package / "include")

    def package_info(self):
        self.info.set_property("cmake_file_name", "RapidJSON")
        self.info.set_property("cmake_target_name", "rapidjson")
        self.info.bindirs = []
        self.info.libdirs = []
