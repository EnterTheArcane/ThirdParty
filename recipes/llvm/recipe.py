import os

from thirdparty import RecipeBase
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import copy, get
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository

_SOURCE_SHA256 = {
    "Windows": {
        "X64": {
            "sha256": "d96c2cc1736f4eb7fa43cb9bbdf56d93551a9ae0a9aadb9c99c3c3b2b712a234",
        },
        "ARM": {
            "sha256": "de718c58ebbc5f61d58c17b90457fcf42983bc2c4a4aba3e010d108713bfd7f1",
        },
    },
    "Linux": {
        "X64": {
            "sha256": "df0e1ecf16caf3489a272a5eea4eec9b0d82878f6477fa309504f918a0006384",
        },
        "ARM": {
            "sha256": "805efad2bb91cb4967fa569e0881d10c0f69c04461cf671cccbae19f547acc34",
        },
    },
    "Mac": {
        "ARM": {
            "sha256": "f260f4f7c0d430828a81ae8a3826a1d63fc0963ec2459489308cc23b1f7eab4f",
        },
    },
}


class Recipe(RecipeBase):
    name = "llvm"
    version = "22.1.8"
    license = "Apache-2.0"

    def latest_version(self):
        repo = GithubRepository(self, "llvm/llvm-project")
        tag = repo.latest_release
        return Version(tag.removeprefix("llvmorg-"))

    def validate(self):
        os_name = str(self.settings.os)
        arch = str(self.settings.arch)
        if os_name not in _SOURCE_SHA256 or arch not in _SOURCE_SHA256[os_name]:
            raise RecipeInvalidConfiguration(f"{self.name} has no prebuilt binaries for {os_name}/{arch}")

    def build(self):
        sha256 = _SOURCE_SHA256[str(self.settings.os)][str(self.settings.arch)]["sha256"]
        get(self, url=self._source_url, sha256=sha256, destination=self.folders.build, strip_root=True)

    def package(self):
        for subdir in ("bin", "include", "lib", "libexec", "share"):
            src = self.folders.build / subdir
            dst = self.folders.package / subdir
            if os.path.isdir(src):
                copy(self, "*", src=src, dst=dst)

    def package_info(self):
        bin_dir = self.folders.package / "bin"
        self.info.buildenv.prepend_path("PATH", bin_dir)
        self.info.buildenv.define_path("LLVM_DIR", self.folders.package)
        self.info.buildenv.define_path("LIBCLANG_PATH", self.folders.package / "lib")
        self.info.conf.tools.llvm.dir = self.folders.package

    @property
    def _source_url(self):
        base_url = f"https://github.com/llvm/llvm-project/releases/download/llvmorg-{self.version}"
        match (str(self.settings.os), str(self.settings.arch)):
            case ("Windows", "X64"):
                return f"{base_url}/clang+llvm-{self.version}-x86_64-pc-windows-msvc.tar.xz"
            case ("Windows", "ARM"):
                return f"{base_url}/clang+llvm-{self.version}-aarch64-pc-windows-msvc.tar.xz"
            case ("Linux", "X64"):
                return f"{base_url}/LLVM-{self.version}-Linux-X64.tar.xz"
            case ("Linux", "ARM"):
                return f"{base_url}/LLVM-{self.version}-Linux-ARM64.tar.xz"
            case ("Mac", "ARM"):
                return f"{base_url}/LLVM-{self.version}-macOS-ARM64.tar.xz"
            case _:
                raise RecipeInvalidConfiguration(f"{self.name} has no prebuilt binaries for {self.settings.os}/{self.settings.arch}")
