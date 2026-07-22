import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty._internal.model.settings import Settings
from thirdparty._internal.util import detect as detect_util
from thirdparty.errors import RecipeException


class SettingsTests(unittest.TestCase):
    def _settings(self, **overrides):
        values = {"os": "Linux", "arch": "X64", "build_type": "Release"}
        values.update(overrides)
        return Settings(**values)

    def test_arch_rejects_universal_arch_values(self):
        settings = self._settings()

        with self.assertRaisesRegex(RecipeException, "Invalid setting 'ARM\\|X64'"):
            settings.arch = "ARM|X64"

    def test_arch_accepts_single_arch_values(self):
        settings = self._settings()

        settings.arch = "ARM"

        self.assertEqual(settings.arch, "ARM")

    def test_required_settings_reject_none(self):
        with self.assertRaisesRegex(RecipeException, "Setting 'os' cannot be None"):
            self._settings(os=None)

        settings = self._settings()
        with self.assertRaisesRegex(RecipeException, "Setting 'build_type' cannot be None"):
            settings.build_type = None

    def test_settings_use_none_for_removed_standards(self):
        settings = self._settings(
            compiler_c_standard="11", compiler_cxx_standard="17", compiler_libcxx="libc++")

        settings.compiler_c_standard = None
        settings.compiler_cxx_standard = None
        settings.compiler_libcxx = None

        self.assertIsNone(settings.compiler_c_standard)
        self.assertIsNone(settings.compiler_cxx_standard)
        self.assertIsNone(settings.compiler_libcxx)

    def test_settings_preserve_int_os_api_level(self):
        settings = self._settings(os="Android", os_api_level=24)

        self.assertEqual(settings.os_api_level, 24)

    def test_detect_settings_defaults_ios_to_latest_device_sdk(self):
        with (
            patch.object(detect_util, "_machine_os", return_value="Mac"),
            patch.object(detect_util, "_machine_arch", return_value="X64"),
            patch.object(detect_util, "_detect_apple_clang_version", return_value="17"),
        ):
            settings = detect_util.detect_settings(target_os="iOS")

        self.assertEqual(settings.os, "iOS")
        self.assertEqual(settings.arch, "ARM")
        self.assertEqual(settings.os_sdk, "iphoneos")
        self.assertIsNone(settings.os_sdk_version)

    def test_detect_settings_defaults_ios_x64_to_simulator_sdk(self):
        with (
            patch.object(detect_util, "_machine_os", return_value="Mac"),
            patch.object(detect_util, "_machine_arch", return_value="ARM"),
            patch.object(detect_util, "_detect_apple_clang_version", return_value="17"),
        ):
            settings = detect_util.detect_settings(target_os="iOS", target_arch="X64")

        self.assertEqual(settings.arch, "X64")
        self.assertEqual(settings.os_sdk, "iphonesimulator")

    def test_detect_platform_tag_uses_ios_device_default(self):
        with patch.object(detect_util, "_machine_arch", return_value="X64"):
            self.assertEqual(detect_util.detect_platform_tag(target_os="iOS"), "ios-arm")


if __name__ == "__main__":
    unittest.main()
