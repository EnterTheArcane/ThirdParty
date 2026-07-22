import os

from thirdparty import RecipeBase
from thirdparty.files import copy, get, save
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "meson"
    version = "1.11.2"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "mesonbuild/meson")
        return Version(repo.latest_release)

    def requirements(self):
        self.requires_tool("ninja")

    def build(self):
        get(
            self,
            url=f"https://github.com/mesonbuild/meson/releases/download/{self.version}/meson-{self.version}.tar.gz",
            sha256="698feae069cef3ecd4d7aaf281d7df359bdfcf555a9a1564383d3b913fa8a736",
            destination=self.folders.build,
            strip_root=True)

    def package(self):
        dst = self.folders.package / "bin"
        copy(self, "mesonbuild/*", src=self.folders.build, dst=dst, keep_path=True)
        copy(self, "COPYING", src=self.folders.build, dst=self.folders.package / "licenses")
        if str(self.settings.os) == "Windows":
            copy(self, "meson.py", src=self.folders.build, dst=dst)
            save(
                self, dst / "meson.cmd",
                '@python "%~dp0meson.py" %*\n')
        else:
            # On Unix the source launcher's shebang is honoured directly. Copy it as
            # "meson" so dependents keep seeing the same command on PATH.
            import shutil
            import stat
            os.makedirs(dst, exist_ok=True)
            meson_path = dst / "meson"
            shutil.copy2(self.folders.build / "meson.py", meson_path)
            os.chmod(meson_path, os.stat(meson_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def package_info(self):
        self.info.libdirs = []
        self.info.includedirs = []
        bin_dir = self.folders.package / "bin"
        self.info.buildenv.prepend_path("PATH", bin_dir)
