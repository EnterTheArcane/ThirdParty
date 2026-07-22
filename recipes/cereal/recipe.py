from thirdparty import RecipeBase, RecipeOptions
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class _Options(RecipeOptions):
    thread_safe: bool = False


class Recipe(RecipeBase[_Options]):
    name = "cereal"
    version = "1.3.2"
    license = "BSD-3-Clause"

    def latest_version(self):
        repo = GithubRepository(self, "USCiLab/cereal")
        return Version(repo.latest_release.removeprefix("v"))

    def source(self):
        get(
            self,
            url=f"https://github.com/USCiLab/cereal/archive/v{self.version}.tar.gz",
            sha256="16a7ad9b31ba5880dac55d62b5d6f243c3ebc8d46a3514149e56b5e7ea81f85f",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "include/*", src=self.folders.source, dst=self.folders.package)

    def package_info(self):
        self.info.set_property("cmake_file_name", "cereal")
        self.info.set_property("cmake_target_name", "cereal::cereal")
        self.info.bindirs = []
        self.info.libdirs = []
        if self.options.thread_safe:
            self.info.defines = ["CEREAL_THREAD_SAFE=1"]
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.info.system_libs.append("pthread")
