from thirdparty import RecipeBase
from thirdparty.errors import RecipeException
from thirdparty.files import copy, get, load, save, apply_patches
from thirdparty.scm import GithubRepository, Version


class Recipe(RecipeBase):
    name = "gnu-config"
    version = "2024.07.28"
    license = "GPL-3.0-or-later", "autoconf-special-exception"

    def latest_version(self):
        date = GithubRepository(self, "build2/config").latest_commit_date()
        return Version(f"{date[:4]}.{date[4:6]}.{date[6:]}")

    def source(self):
        get(
            self,
            url="https://github.com/build2/config/archive/00b15927496058d23e6258a28d8996f87cf1f191.tar.gz",
            sha256="1b32d68b3db54f53f919f335360d9d0a077839799856c1b8cc6ccb31c255a6b9",
            destination=self.folders.source,
            strip_root=True)
        apply_patches(self)

    def package(self):
        save(self, self.folders.package / "licenses" / "COPYING", self._extract_license())
        copy(self, "config.guess", src=self.folders.source, dst=self.folders.package / "bin")
        copy(self, "config.sub", src=self.folders.source, dst=self.folders.package / "bin")

    def package_info(self):
        self.info.includedirs = []
        self.info.libdirs = []

        bin_path = self.folders.package / "bin"
        self.info.conf.tools.gnu_config.config_guess = bin_path / "config.guess"
        self.info.conf.tools.gnu_config.config_sub = bin_path / "config.sub"

    def _extract_license(self):
        txt_lines = load(self, self.folders.source / "config.guess").splitlines()
        start_index = None
        end_index = None
        for line_i, line in enumerate(txt_lines):
            if start_index is None:
                if "This file is free" in line:
                    start_index = line_i
            if end_index is None:
                if "Please send patches" in line:
                    end_index = line_i
        if not all((start_index, end_index)):
            raise RecipeException("Failed to extract the license")
        return "\n".join(txt_lines[start_index:end_index])
