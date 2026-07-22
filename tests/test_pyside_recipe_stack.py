import ast
import unittest
from pathlib import Path

from thirdparty import RecipeBase
from thirdparty._internal.graph import Graph
from thirdparty._internal.loader import make_probe_recipe, resolve_version, try_load_recipe_class
from thirdparty._internal.model.conf import Conf
from thirdparty._internal.util.detect_api import detect_arch


ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"


class PySideRecipeStackTests(unittest.TestCase):
    def _recipe_class(self, name: str) -> type[RecipeBase]:
        recipe_class = try_load_recipe_class(RECIPES, name)
        self.assertIsNotNone(recipe_class, f"failed to load {name}")
        assert recipe_class is not None
        return recipe_class

    def test_cross_dependency_boundaries(self):
        # Keep this a cross-build test on both x86_64 CI hosts and ARM64 developer machines.
        target_arch = "X64" if detect_arch() == "ARM" else "ARM"
        graph = Graph.build(
            RECIPES,
            ["pyside", "shiboken", "shiboken-generator"],
            "Release",
            target_os="Linux",
            target_arch=target_arch)

        self.assertEqual(graph["pyside"].host_deps, ["cpython", "qt", "shiboken"])
        self.assertEqual(
            graph["pyside"].tool_deps,
            ["cmake", "cpython", "shiboken-generator", "qt"])
        self.assertNotIn("pyside", graph["pyside"].all_deps)

        self.assertEqual(graph["shiboken"].host_deps, ["cpython", "qt"])
        self.assertEqual(
            graph["shiboken"].tool_deps,
            ["cmake", "cpython", "shiboken-generator", "qt"])

        self.assertEqual(graph["shiboken-generator"].host_deps, [])
        self.assertEqual(
            graph["shiboken-generator"].tool_deps,
            ["cmake", "cpython", "llvm", "qt"])

    def test_native_recipes_do_not_add_host_qt_as_a_tool(self):
        graph = Graph.build(
            RECIPES,
            ["pyside", "shiboken"],
            "Release")

        self.assertEqual(
            graph["pyside"].tool_deps,
            ["cmake", "cpython", "shiboken-generator"])
        self.assertEqual(
            graph["shiboken"].tool_deps,
            ["cmake", "cpython", "shiboken-generator"])

    def test_qt_has_no_static_build_option_or_branch(self):
        recipe_class = self._recipe_class("qt")
        recipe = make_probe_recipe(
            recipe_class, RECIPES, "qt", resolve_version(recipe_class), "Release")
        source = (RECIPES / "qt" / "recipe.py").read_text(encoding="utf-8")

        self.assertIsNone(recipe.options.get_safe("shared"))
        self.assertNotIn("self.options.shared", source)
        self.assertNotIn('glob("objects-*/")', source)
        self.assertIn('tc.variables["BUILD_SHARED_LIBS"] = True', source)
        self.assertIn('tc.variables["FEATURE_static"] = "OFF"', source)
        self.assertIn("tc.add_rpath_link = True", source)

    def test_clean_public_configuration_interface(self):
        conf = Conf()
        conf.tools.shiboken.generator = "/tools/bin/shiboken6"
        conf.tools.shiboken.generator_root = "/tools"
        conf.tools.pyside.root = "/pyside"

        restored = Conf().deserialize_state(conf.serialize_state())
        self.assertEqual(restored.tools.shiboken.generator, "/tools/bin/shiboken6")
        self.assertEqual(restored.tools.shiboken.generator_root, "/tools")
        self.assertEqual(restored.tools.pyside.root, "/pyside")
        self.assertFalse(hasattr(restored.tools, "pyside6"))
        self.assertFalse(hasattr(restored.tools.pyside, "shiboken6_generator"))

    def test_xkbcommon_exports_qt_expected_cmake_contract(self):
        recipe_class = self._recipe_class("xkbcommon")
        recipe = make_probe_recipe(
            recipe_class, RECIPES, "xkbcommon", resolve_version(recipe_class), "Release")
        recipe.package_info()

        self.assertEqual(recipe.info.get_property("cmake_file_name"), "XKB")
        self.assertEqual(
            recipe.info.get_property("cmake_config_version_compat"),
            "AnyNewerVersion",
        )
        self.assertEqual(
            recipe.info.components["xkbcommon"].get_property("cmake_target_name"),
            "XKB::XKB")

    def test_pyside_wrapper_contains_only_binding_phases(self):
        wrapper = (RECIPES / "pyside" / "CMakeLists.txt").read_text(encoding="utf-8")
        recipe = (RECIPES / "pyside" / "recipe.py").read_text(encoding="utf-8")
        generator_recipe = (
            RECIPES / "shiboken-generator" / "recipe.py").read_text(encoding="utf-8")
        self.assertIn("sources/pyside6", wrapper)
        self.assertIn("sources/pyside-tools", wrapper)
        self.assertNotIn("sources/shiboken6_generator", wrapper)
        self.assertNotIn('add_subdirectory("${PYSIDE_SOURCE_DIR}/sources/shiboken6"', wrapper)
        self.assertIn('tc.variables["CMAKE_SKIP_INSTALL_RPATH"] = True', recipe)
        self.assertNotIn("QT_SKIP_AUTO_PLUGIN_INCLUSION", recipe)
        self.assertIn('bin_dir / "pyside6-uic"', recipe)
        self.assertIn('bin_dir / "pyside6-rcc"', recipe)
        self.assertIn("DYLD_FALLBACK_LIBRARY_PATH", recipe)
        self.assertIn("QT_PLUGIN_PATH", recipe)
        self.assertIn(
            'tc.variables["CMAKE_SKIP_INSTALL_RPATH"] = True', generator_recipe)

    def test_native_pyi_generation_uses_external_shiboken_package(self):
        recipe = (RECIPES / "pyside" / "recipe.py").read_text(encoding="utf-8")
        patch = (RECIPES / "pyside" / "patches" /
                 "0001-external-shiboken-python-path.patch").read_text(encoding="utf-8")

        self.assertIn('tc.variables["SHIBOKEN_PYTHON_MODULE_DIR"]', recipe)
        self.assertIn("if(NOT SHIBOKEN_PYTHON_MODULE_DIR)", patch)
        self.assertNotIn("DISABLE_PYI", recipe)

    def test_single_use_recipe_logic_is_inline(self):
        recipe = (RECIPES / "pyside" / "recipe.py").read_text(encoding="utf-8")

        self.assertNotIn("def _shiboken_system_processor", recipe)
        self.assertIn('processor = "AMD64" if self.settings.os == "Windows" else "x86_64"', recipe)
        self.assertIn('}.get(self.settings.os, "aarch64")', recipe)

        for name in ("pyside", "shiboken", "shiboken-generator"):
            tree = ast.parse((RECIPES / name / "recipe.py").read_text(encoding="utf-8"))
            for definition in tree.body:
                if not isinstance(definition, ast.FunctionDef) or not definition.name.startswith("_"):
                    continue
                references = sum(
                    isinstance(node, ast.Name) and node.id == definition.name
                    for node in ast.walk(tree)
                )
                self.assertGreaterEqual(
                    references,
                    2,
                    f"{name}.{definition.name} should be inline or have multiple callers",
                )


if __name__ == "__main__":
    unittest.main()
