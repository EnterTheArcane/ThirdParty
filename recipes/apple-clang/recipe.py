from thirdparty import RecipeBase
from thirdparty._internal.model.settings import Settings
from thirdparty.apple import XCRun
from thirdparty.errors import RecipeInvalidConfiguration

_APPLE_OSES = ("Mac", "iOS", "tvOS", "visionOS")


class Recipe(RecipeBase):
    name = "apple-clang"
    version = "1"
    license = "Apple Xcode License"

    def validate(self):
        if str(self.settings_build.os) != "Mac":
            raise RecipeInvalidConfiguration("apple-clang requires a macOS build machine (Xcode CLT)")
        if str(self.settings.os) not in _APPLE_OSES:
            raise RecipeInvalidConfiguration(
                f"apple-clang only targets Apple platforms, not {self.settings.os}")

    def toolchain_settings(self, settings: Settings):
        settings.compiler = "apple-clang"
        settings.compiler_libcxx = "libc++"

    def requirements(self):
        self.requires("apple-sdk")

    def package_info(self):
        self.info.redistributable = False
        self.info.includedirs = []
        self.info.libdirs = []
        self.info.bindirs = []

        xcrun = XCRun(self)
        self.info.toolchain.family = "apple-clang"
        self.info.toolchain.front_kind = "clang"
        self.info.toolchain.compilers = {"c": xcrun.cc, "cpp": xcrun.cxx}
        self.info.toolchain.ar = xcrun.ar
        self.info.toolchain.ranlib = xcrun.ranlib
        self.info.toolchain.strip = xcrun.strip
        self.info.toolchain.stdlib = str(self.settings.compiler_libcxx) if self.settings.compiler_libcxx else "libc++"

        sdk = self.dependencies["apple-sdk"].info
        self.info.toolchain.apple_sysroot = sdk.get_property("sdk_path")
        self.info.toolchain.apple_sdk_name = sdk.get_property("sdk_name")
        self.info.toolchain.apple_min_version_flag = sdk.get_property("min_version_flag")
