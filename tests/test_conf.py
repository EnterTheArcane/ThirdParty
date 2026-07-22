import unittest
from pathlib import Path

from thirdparty._internal.model.conf import Conf


class ConfTest(unittest.TestCase):
    def test_defaults_are_empty_and_typed(self):
        conf = Conf()

        self.assertFalse(conf)
        self.assertEqual(conf.tools.build.cflags, [])
        self.assertEqual(conf.tools.build.compiler_executables, {})
        self.assertIsNone(conf.tools.gnu.pkg_config)

    def test_direct_assignment_marks_conf_non_empty(self):
        conf = Conf()

        conf.tools.gnu.pkg_config = "pkgconf"
        conf.tools.build.cflags.append("-O2")
        conf.tools.build.compiler_executables["c"] = Path("/usr/bin/clang")

        self.assertTrue(conf)
        self.assertEqual(conf.tools.gnu.pkg_config, "pkgconf")
        self.assertEqual(conf.tools.build.cflags, ["-O2"])
        self.assertEqual(conf.tools.build.compiler_executables["c"], Path("/usr/bin/clang"))

    def test_copy_is_deep(self):
        conf = Conf()
        conf.tools.build.cflags.append("-Wall")

        copied = conf.copy()
        copied.tools.build.cflags.append("-Wextra")

        self.assertEqual(conf.tools.build.cflags, ["-Wall"])
        self.assertEqual(copied.tools.build.cflags, ["-Wall", "-Wextra"])

    def test_compose_conf_fills_empty_values_and_preserves_current_scalars(self):
        current = Conf()
        current.tools.gnu.pkg_config = "pkgconf"
        current.tools.build.compiler_executables["c"] = "clang"

        other = Conf()
        other.tools.gnu.pkg_config = "pkg-config"
        other.tools.build.cflags.append("-fPIC")
        other.tools.build.compiler_executables["c"] = "gcc"
        other.tools.build.compiler_executables["cpp"] = "g++"

        current.compose_conf(other)

        self.assertEqual(current.tools.gnu.pkg_config, "pkgconf")
        self.assertEqual(current.tools.build.cflags, ["-fPIC"])
        self.assertEqual(
            current.tools.build.compiler_executables,
            {"c": "clang", "cpp": "g++"})

    def test_serialize_state_uses_nested_field_names_and_json_safe_paths(self):
        conf = Conf()
        conf.tools.gnu_config.config_guess = Path("/tmp/config.guess")
        conf.tools.build.compiler_executables["c"] = Path("/usr/bin/clang")
        conf.core.net.http.client_cert = (Path("/tmp/client.crt"), Path("/tmp/client.key"))

        state = conf.serialize_state()

        self.assertEqual(state["tools"]["gnu_config"]["config_guess"], "/tmp/config.guess")
        self.assertEqual(state["tools"]["build"]["compiler_executables"]["c"], "/usr/bin/clang")
        self.assertEqual(state["core"]["net"]["http"]["client_cert"], ["/tmp/client.crt", "/tmp/client.key"])

        restored = Conf().deserialize_state(state)

        self.assertEqual(restored.tools.gnu_config.config_guess, "/tmp/config.guess")
        self.assertEqual(restored.tools.build.compiler_executables["c"], "/usr/bin/clang")
        self.assertEqual(restored.core.net.http.client_cert, ("/tmp/client.crt", "/tmp/client.key"))

    def test_build_dependency_metadata_propagates_through_compose(self):
        recipe_conf = Conf()
        dep_conf = Conf()
        dep_conf.tools.microsoft.bash.path = "/msys64/usr/bin/bash.exe"
        dep_conf.tools.build.compiler_executables["asm"] = "/tools/nasm"
        dep_conf.tools.gnu_config.config_guess = "/tools/config.guess"
        dep_conf.tools.gnu_config.config_sub = "/tools/config.sub"

        recipe_conf.compose_conf(dep_conf)

        self.assertEqual(recipe_conf.tools.microsoft.bash.path, "/msys64/usr/bin/bash.exe")
        self.assertEqual(recipe_conf.tools.build.compiler_executables["asm"], "/tools/nasm")
        self.assertEqual(recipe_conf.tools.gnu_config.config_guess, "/tools/config.guess")
        self.assertEqual(recipe_conf.tools.gnu_config.config_sub, "/tools/config.sub")


if __name__ == "__main__":
    unittest.main()
