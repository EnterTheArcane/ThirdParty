from thirdparty import RecipeBase
from thirdparty.files import get, copy
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "ms-gsl"
    version = "4.2.2"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "microsoft/GSL")
        return Version(repo.latest_release.removeprefix("v"))

    def source(self):
        get(
            self,
            url=f"https://github.com/microsoft/GSL/archive/v{self.version}.tar.gz",
            sha256="59e2a0a0ea22e8bcf9db2dc4d4bd21212ac6595748295fc27a7e02cf75eac4b5",
            destination=self.folders.source,
            strip_root=True)

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(self, "*", src=self.folders.source / "include", dst=self.folders.package / "include")

    def package_info(self):
        self.info.set_property("cmake_file_name", "Microsoft.GSL")
        self.info.set_property("cmake_target_name", "Microsoft.GSL::GSL")
        self.info.bindirs = []
        self.info.libdirs = []
