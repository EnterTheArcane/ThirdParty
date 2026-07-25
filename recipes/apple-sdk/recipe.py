from thirdparty import RecipeBase
from thirdparty.apple import XCRun
from thirdparty.apple.utils import apple_min_version_flag, get_apple_sdk_fullname
from thirdparty.errors import RecipeInvalidConfiguration

_APPLE_OSES = ("Mac", "iOS", "tvOS", "visionOS")


class Recipe(RecipeBase):
    name = "apple-sdk"
    version = "1"
    license = "Apple SDK License"

    def validate(self):
        if str(self.settings_build.os) != "Mac":
            raise RecipeInvalidConfiguration(
                "Apple SDKs can only be located on a macOS build machine (Xcode CLT)")
        if str(self.settings.os) not in _APPLE_OSES:
            raise RecipeInvalidConfiguration(
                f"{self.name} only supports Apple targets, not {self.settings.os}")

    def package_info(self):
        self.info.redistributable = False
        self.info.includedirs = []
        self.info.libdirs = []
        self.info.bindirs = []

        xcrun = XCRun(self)
        sdk_path = xcrun.sdk_path
        if not sdk_path:
            raise RecipeInvalidConfiguration(
                f"xcrun could not resolve an SDK path for '{self.settings.os_sdk or 'macosx'}' - "
                f"install the Xcode Command Line Tools (xcode-select --install)")
        self.info.set_property("sdk_path", str(sdk_path))
        try:
            self.info.set_property("sdk_name", get_apple_sdk_fullname(self))
        except Exception:
            self.info.set_property("sdk_name", str(self.settings.os_sdk or "macosx"))
        min_version = apple_min_version_flag(self)
        if min_version:
            self.info.set_property("min_version_flag", min_version)
        sdk_version = xcrun.sdk_version
        if sdk_version:
            self.info.set_property("sdk_version", str(sdk_version))
