import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty.cmake.toolchain.blocks import GenericSystemBlock


class CMakeToolchainTests(unittest.TestCase):
    def test_apple_26_versions_map_to_darwin_25(self):
        self.assertEqual(GenericSystemBlock._get_darwin_version("Mac", "26.5"), "25")
        self.assertEqual(GenericSystemBlock._get_darwin_version("iOS", "26.0"), "25")
        self.assertEqual(GenericSystemBlock._get_darwin_version("tvOS", "26.0"), "25")
        self.assertEqual(GenericSystemBlock._get_darwin_version("visionOS", "26.0"), "25")


if __name__ == "__main__":
    unittest.main()
