import shutil

from thirdparty import RecipeBase
from thirdparty._internal.model.settings import Settings
from thirdparty.errors import RecipeInvalidConfiguration

# Target-triplet-prefixed compilers drive Linux cross builds (x64 -> ARM) and match the
# minimal build container, which ships only triplet-prefixed gcc (no bare gcc/cc).
_TRIPLETS = {"X64": "x86_64-linux-gnu", "ARM": "aarch64-linux-gnu"}
_BINUTILS = ("ar", "ranlib", "nm", "strip", "objcopy")


class Recipe(RecipeBase):
    name = "gcc"
    version = "1"
    license = "GPL-3.0-with-GCC-exception"

    def validate(self):
        if str(self.settings_build.os) != "Linux" or str(self.settings.os) != "Linux":
            raise RecipeInvalidConfiguration("gcc is only supported for Linux -> Linux builds")
        if self._find("gcc", "g++") is None:
            raise RecipeInvalidConfiguration(
                f"no gcc found on PATH for target {self.settings.arch} "
                f"(looked for {_TRIPLETS[str(self.settings.arch)]}-gcc and gcc)")

    def toolchain_settings(self, settings: Settings):
        settings.compiler = "gcc"
        settings.compiler_libcxx = "libstdc++11"

    def package_info(self):
        self.info.redistributable = False
        self.info.includedirs = []
        self.info.libdirs = []
        self.info.bindirs = []

        found = self._find("gcc", "g++")
        if found is None:
            raise RecipeInvalidConfiguration("no gcc found on PATH")
        cc, cxx, prefix = found

        self.info.toolchain.family = "gcc"
        self.info.toolchain.front_kind = "gnu"
        self.info.toolchain.compilers = {"c": cc, "cpp": cxx}
        for tool in _BINUTILS:
            exe = shutil.which(f"{prefix}{tool}") or shutil.which(tool)
            if exe:
                setattr(self.info.toolchain, tool, exe)
        self.info.toolchain.target_triple = _TRIPLETS[str(self.settings.arch)]
        self.info.toolchain.stdlib = str(self.settings.compiler_libcxx) if self.settings.compiler_libcxx else "libstdc++11"

    def _find(self, cc_name: str, cxx_name: str) -> "tuple[str, str, str] | None":
        triplet = _TRIPLETS.get(str(self.settings.arch))
        if triplet:
            cc = shutil.which(f"{triplet}-{cc_name}")
            cxx = shutil.which(f"{triplet}-{cxx_name}")
            if cc and cxx:
                return cc, cxx, f"{triplet}-"
        cc = shutil.which(cc_name)
        cxx = shutil.which(cxx_name)
        if cc and cxx:
            return cc, cxx, ""
        return None
