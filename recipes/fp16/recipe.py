from thirdparty import RecipeBase
from thirdparty.files import get, copy
from thirdparty.scm import GithubRepository, Version


class Recipe(RecipeBase):
    name = "fp16"
    version = "20260620"
    license = "MIT"

    def latest_version(self):
        return Version(GithubRepository(self, "Maratyszcza/FP16").latest_commit_date())

    def source(self):
        get(
            self,
            url="https://github.com/Maratyszcza/FP16/archive/782eea126dc5c755827be751a099eb01826175cf.zip",
            sha256="f7f8b1ff0bc87e366c89dee192708cbf9609bc7e204b2d88b514364eb8dbb7ba",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "*.h", src=self.folders.source / "include", dst=self.folders.package / "include")

    def package_info(self):
        self.info.set_property("cmake_file_name", "fp16")
        self.info.set_property("cmake_target_name", "fp16::fp16")
        self.info.bindirs = []
        self.info.libdirs = []
