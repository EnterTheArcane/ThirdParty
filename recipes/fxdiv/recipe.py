from thirdparty import RecipeBase
from thirdparty.files import get, copy
from thirdparty.scm import GithubRepository, Version


class Recipe(RecipeBase):
    name = "fxdiv"
    version = "20201209"
    license = "MIT"

    def latest_version(self):
        return Version(GithubRepository(self, "Maratyszcza/FXdiv").latest_commit_date())

    def source(self):
        get(
            self,
            url="https://github.com/Maratyszcza/FXdiv/archive/63058eff77e11aa15bf531df5dd34395ec3017c8.zip",
            sha256="3d7b0e9c4c658a84376a1086126be02f9b7f753caa95e009d9ac38d11da444db",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "*", src=self.folders.source / "include", dst=self.folders.package / "include")

    def package_info(self):
        self.info.set_property("cmake_file_name", "fxdiv")
        self.info.set_property("cmake_target_name", "fxdiv::fxdiv")
        self.info.bindirs = []
        self.info.libdirs = []
