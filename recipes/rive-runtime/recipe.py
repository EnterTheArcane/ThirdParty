from thirdparty import RecipeBase
from thirdparty.env import Environment, VirtualBuildEnv
from thirdparty.files import apply_patches, copy, get
from thirdparty.premake import Premake, PremakeDeps, PremakeToolchain
from thirdparty.scm import Version
from thirdparty.scm.github import GithubRepository


class Recipe(RecipeBase):
    name = "rive-runtime"
    version = "0.1.204"
    license = "MIT"

    def latest_version(self):
        repo = GithubRepository(self, "rive-app/rive-runtime")
        return Version(repo.latest_tag("runtime-v").removeprefix("runtime-v"))

    def requirements(self):
        self.requires_tool("premake")

    def source(self):
        get(
            self,
            url=f"https://github.com/rive-app/rive-runtime/archive/refs/tags/runtime-v{self.version}.tar.gz",
            sha256="9d282145afa918cc419512a3ba842f03028755ec18f8afe845369b7c04613016",
            destination=self.folders.source,
            strip_root=True)

        deps_dir = self.folders.source / "dependencies"

        # rive-app fork of harfbuzz (branch rive_13.1.1, pinned to commit)
        get(
            self,
            url="https://github.com/rive-app/harfbuzz/archive/08d34675f64b1ac4880f4f10c9fd474a56dd4399.tar.gz",
            sha256="0c36546f9cadbed2a5c3d7b29cb94024bdbf553fb7cde7278a24a3938c195bc0",
            destination=deps_dir / "rive-app_harfbuzz_rive_13.1.1",
            strip_root=True)

        # SheenBidi (tag)
        get(
            self,
            url="https://github.com/Tehreer/SheenBidi/archive/refs/tags/v2.6.tar.gz",
            sha256="f538f51a7861dd95fb9e3f4ad885f39204b5c670867019b5adb7c4b410c8e0d9",
            destination=deps_dir / "Tehreer_SheenBidi_v2.6",
            strip_root=True)

        # rive-app fork of yoga (branch rive_changes_v2_0_1_2, pinned to commit)
        get(
            self,
            url="https://github.com/rive-app/yoga/archive/b827168e5e66c56b3117660a12607fe4f54ea33c.tar.gz",
            sha256="952d0a3900d04ae6a10ba5aa18a0c619c43271a5ace7240e510bfe6fb91ebd4c",
            destination=deps_dir / "rive-app_yoga_rive_changes_v2_0_1_2",
            strip_root=True)

        # rive-app fork of miniaudio (branch rive_changes_5, pinned to commit)
        get(
            self,
            url="https://github.com/rive-app/miniaudio/archive/3a8b070f80e203a35ec763c5118da20805a90d5a.tar.gz",
            sha256="a464609bba1294675e65e559277fe7ae0b1b7732011f537493133c486c609c76",
            destination=deps_dir / "rive-app_miniaudio_rive_changes_5",
            strip_root=True)
        apply_patches(self)

    def generate(self):
        deps = PremakeDeps(self)
        deps.generate()
        # Generate the dependency environment before the toolchain: on Linux the
        # toolchain adds the target-triplet CC/CXX exports to the same script and
        # must be the final writer for cross builds.
        VirtualBuildEnv(self).generate()
        tc = PremakeToolchain(self)
        tc.generate()

    def build(self):
        config = "release" if str(self.settings.build_type) == "Release" else "debug"

        _arch_map = {"X64": "x64", "ARM": "arm64"}

        premake = Premake(self)
        premake.luafile = (self.folders.source / "premake5_v2.lua").as_posix()
        if premake.action == "vs2026":
            premake.action = "vs2022"
        premake.arguments["config"] = config
        # Put generated build files directly in build_folder so premake.build() can find them
        premake.arguments["out"] = "."
        premake.arguments["arch"] = _arch_map.get(str(self.settings.arch), "x64")
        if self.settings.os == "Windows":
            premake.arguments["toolset"] = "msc"
        elif self.settings.compiler == "clang":
            premake.arguments["toolset"] = "clang"
        else:
            premake.arguments["toolset"] = "gcc"
        premake.arguments["with_rive_text"] = ""
        premake.arguments["with_rive_layout"] = ""

        # rive_build_config.lua is found via PREMAKE_PATH; dependency source via DEPENDENCIES
        env = Environment()
        env.define("PREMAKE_PATH", (self.folders.source / "build").as_posix())
        env.define("DEPENDENCIES", (self.folders.source / "dependencies").as_posix())

        # configure() injects --arch from RECIPE_TO_PREMAKE_ARCH when the recipe toolchain file exists,
        # but rive uses its own --arch option with different values (x64 not x86_64).
        # Hide the toolchain path so configure() takes the legacy code path and uses our arch arg.
        _real_tc = premake._premake_recipe_toolchain  # type: ignore[reportPrivateUsage]
        premake._premake_recipe_toolchain = _real_tc.parent / "_disabled_recipe_toolchain.premake5.lua"  # type: ignore[reportPrivateUsage]
        try:
            with env.vars(self).apply():
                premake.configure()
        finally:
            premake._premake_recipe_toolchain = _real_tc  # type: ignore[reportPrivateUsage]

        premake.build(workspace="rive", targets=["rive"], configuration="default")

    def package(self):
        copy(self, "LICENSE", src=self.folders.source, dst=self.folders.package / "licenses")
        copy(
            self, "*.h", src=self.folders.source / "include",
            dst=self.folders.package / "include", keep_path=True)
        copy(self, "*.a", src=self.folders.build, dst=self.folders.package / "lib", keep_path=False)
        copy(self, "*.lib", src=self.folders.build, dst=self.folders.package / "lib", keep_path=False)

    def package_info(self):
        self.info.set_property("cmake_file_name", "rive")
        self.info.set_property("cmake_target_name", "rive::rive")
        self.info.libs = ["rive"]
        if self.settings.os == "Windows":
            self.info.defines = ["_USE_MATH_DEFINES", "NOMINMAX"]
        elif self.settings.os in ["Linux", "FreeBSD"]:
            self.info.system_libs = ["m", "pthread"]
        elif self.settings.os == "Mac":
            self.info.frameworks = ["CoreText", "CoreGraphics", "CoreFoundation"]
