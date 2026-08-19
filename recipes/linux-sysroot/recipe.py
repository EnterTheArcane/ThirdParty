import io
import json
import os
import tarfile
from pathlib import Path

from thirdparty import RecipeBase
from thirdparty.errors import RecipeInvalidConfiguration
from thirdparty.files import download

# Hermetic Linux sysroot (glibc + libstdc++ headers/libs for the target arch), assembled
# from Debian trixie packages pinned in sysroot.lock (regenerate it against a newer
# snapshot.debian.org timestamp to upgrade). Debian trixie = glibc 2.41 / gcc-14
# libstdc++, so built binaries require a 2025+ distro at runtime.
_ARCH = {"X64": "amd64", "ARM": "arm64"}


class Recipe(RecipeBase):
    name = "linux-sysroot"
    version = "trixie.1"
    license = "Various (Debian package licenses; see Debian archive)"

    def validate(self):
        if str(self.settings.os) != "Linux":
            raise RecipeInvalidConfiguration(f"{self.name} only supports Linux targets")
        if str(self.settings.arch) not in _ARCH:
            raise RecipeInvalidConfiguration(f"{self.name} has no sysroot for arch {self.settings.arch}")

    def build(self):
        lock = json.loads((self.folders.recipe / "sysroot.lock").read_text(encoding="utf-8"))
        for name, entry in sorted(lock["packages"][_ARCH[str(self.settings.arch)]].items()):
            download(
                self,
                url=f"{lock['base_url']}/{entry['file']}",
                filename=f"{name}.deb",
                sha256=entry["sha256"])

    def package(self):
        for deb in sorted(Path(self.folders.build).glob("*.deb")):
            _extract_deb_data(deb, self.folders.package)
        _make_symlinks_relative(self.folders.package)

    def package_info(self):
        self.info.redistributable = False
        # Consumed via --sysroot by the toolchain provider, never via -I/-L flags.
        self.info.includedirs = []
        self.info.libdirs = []
        self.info.bindirs = []
        self.info.set_property("sysroot_path", str(self.folders.package))


def _extract_deb_data(deb_path: Path, destination: Path):
    # A .deb is a Unix ar archive; the payload is its data.tar.{xz,zst,gz} member.
    with open(deb_path, "rb") as f:
        if f.read(8) != b"!<arch>\n":
            raise RecipeInvalidConfiguration(f"{deb_path.name} is not a .deb archive")
        while header := f.read(60):
            member = header[0:16].decode().strip().rstrip("/")
            size = int(header[48:58].decode().strip())
            data = f.read(size)
            if size % 2:
                f.read(1)
            if member.startswith("data.tar"):
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
                    tar.extractall(destination, filter="tar")
                return
    raise RecipeInvalidConfiguration(f"{deb_path.name} has no data.tar member")


def _make_symlinks_relative(root: Path):
    # Debian packages link with absolute paths (/lib/x86_64-linux-gnu/libc.so.6), which
    # would escape the sysroot; rewrite them relative so --sysroot resolution works.
    if os.name == "nt":
        return
    for path in root.rglob("*"):
        if not path.is_symlink():
            continue
        target = os.readlink(path)
        if not os.path.isabs(target):
            continue
        resolved = root / target.lstrip("/")
        path.unlink()
        path.symlink_to(os.path.relpath(resolved, path.parent))
