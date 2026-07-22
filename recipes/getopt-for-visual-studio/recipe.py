from thirdparty import RecipeBase
from thirdparty.files import apply_patches, copy, get, load, save
from thirdparty.scm import GithubRepository, Version


class Recipe(RecipeBase):
    name = "getopt-for-visual-studio"
    version = "20200308"
    license = "BSD-2-Clause", "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "skandhurkat/Getopt-for-Visual-Studio")
        return Version(repo.latest_commit_date())

    def source(self):
        get(
            self,
            url="https://github.com/skandhurkat/Getopt-for-Visual-Studio/archive/6567b18432b1b4dc0e71f71b8601df28c1ac09f8.zip",
            sha256="d8601e4d04b76ef66a03a62feda39cd0b2636aa1d8af1f971a06c0d567130712",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def package(self):
        save(self, self.folders.package / "licenses" / "LICENSE", self._license_text)
        copy(self, "getopt.h", src=self.folders.source, dst=self.folders.package / "include")

    def package_info(self):
        self.info.bindirs = []
        self.info.libdirs = []

    @property
    def _license_text(self):
        content = load(self, self.folders.source / "getopt.h")
        return "\n".join(list(l.strip() for l in content[content.find("/**", 3):content.find("#pragma")].split("\n")))
