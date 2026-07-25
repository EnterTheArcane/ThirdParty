import sys
import tempfile
import textwrap
import unittest
from collections import OrderedDict
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty import RecipeBase
from thirdparty._internal.methods import _inject_toolchain_requires
from thirdparty._internal.model.conf import Conf
from thirdparty._internal.model.dependencies import RecipeDependencies
from thirdparty._internal.model.info import Info
from thirdparty._internal.model.profile import BuildProfile
from thirdparty._internal.model.refs import RecipeReference
from thirdparty._internal.model.requires import Requirement
from thirdparty._internal.model.settings import Settings
from thirdparty._internal.model.state import RecipeState
from thirdparty._internal.model.toolchain import ToolchainInfo
from thirdparty._internal.toolchains import (
    find_toolchain,
    is_toolchain,
    resolve_settings,
    select_toolchain,
    toolchain_layer,
)
from thirdparty.build.flags import lto_flags
from thirdparty.cmake.toolchain.blocks import LTOBlock, ToolchainProviderBlock
from thirdparty.errors import RecipeException
from thirdparty.microsoft.visual import msvs_toolset


ROOT = Path(__file__).resolve().parents[1]
REAL_RECIPES = ROOT / "recipes"


def _settings(os="Linux", arch="X64", build_type="Release", **fields) -> Settings:
    s = Settings(os=os, arch=arch, build_type=build_type)
    for k, v in fields.items():
        setattr(s, k, v)
    return s


def _make_recipe(name="consumer", settings=None, settings_build=None, deps=None, conf=None, recipe_dir=None):
    class _Recipe(RecipeBase):
        pass

    _Recipe.name = name
    recipe = _Recipe()
    recipe.folders.set_recipe(recipe_dir or (REAL_RECIPES / name))
    settings = settings or _settings()
    recipe._state = RecipeState(
        dependencies=deps or RecipeDependencies(OrderedDict()),
        build_context=False,
        settings=settings,
        settings_build=settings_build or settings,
        conf=conf or Conf(),
        info=Info(set_defaults=True))
    return recipe


def _provider_dep(name: str, tc: "ToolchainInfo | None" = None, build: bool = False):
    dep = _make_recipe(name=name)
    if tc is not None:
        dep._state.info.toolchain = tc
    req = Requirement(RecipeReference(name), build=build, run=build, direct=True)
    return req, dep


def _consumer_with_provider(provider_name="clang", tc=None, settings=None, extra_deps=(), settings_build=None):
    deps = OrderedDict()
    req, dep = _provider_dep(provider_name, tc)
    deps[req] = dep
    for extra_name, extra_tc in extra_deps:
        extra_req, extra_dep = _provider_dep(extra_name, extra_tc)
        deps[extra_req] = extra_dep
    settings = settings or _settings(compiler="clang", compiler_recipe=provider_name)
    return _make_recipe(settings=settings, settings_build=settings_build, deps=RecipeDependencies(deps))


def _write_stub_toolchain(root: Path, name: str, family: str, reject_os=(), default=False):
    (root / name).mkdir(parents=True)
    (root / name / "recipe.py").write_text(textwrap.dedent(f"""
        from thirdparty import RecipeBase
        from thirdparty.errors import RecipeInvalidConfiguration

        class Recipe(RecipeBase):
            name = "{name}"
            version = "1"
            license = "MIT"
            default_toolchain = {default}

            def validate(self):
                if str(self.settings.os) in {tuple(reject_os)!r}:
                    raise RecipeInvalidConfiguration(
                        f"{name} does not support {{self.settings.os}}")

            def toolchain_settings(self, settings):
                settings.compiler = "{family}"
        """), encoding="utf-8")


class BuildProfileTests(unittest.TestCase):
    def test_build_machine_clears_target_and_keeps_compiler(self):
        profile = BuildProfile("Debug", "Linux", "ARM", "clang")
        machine = profile.build_machine()
        self.assertEqual(machine, BuildProfile("Debug", None, None, "clang"))
        self.assertTrue(profile.is_cross)
        self.assertFalse(machine.is_cross)


class SelectToolchainTests(unittest.TestCase):
    def test_default_first_then_validate_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_stub_toolchain(root, "zz-clang", "clang", reject_os=("Mac",), default=True)
            _write_stub_toolchain(root, "aa-gcc", "gcc")
            self.assertEqual(select_toolchain(BuildProfile(target_os="Linux"), root), "zz-clang")
            self.assertEqual(select_toolchain(BuildProfile(target_os="Mac"), root), "aa-gcc")

    def test_explicit_unknown_toolchain_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_stub_toolchain(root, "clang", "clang")
            with self.assertRaisesRegex(RecipeException, "no such toolchain"):
                select_toolchain(BuildProfile(compiler="nonsense"), root)

    def test_explicit_unsupported_toolchain_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_stub_toolchain(root, "clang", "clang", reject_os=("Mac",))
            with self.assertRaisesRegex(RecipeException, "does not support this target"):
                select_toolchain(BuildProfile(target_os="Mac", compiler="clang"), root)

    def test_resolve_settings_tolerates_missing_toolchains(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = resolve_settings(BuildProfile(target_os="Linux"), Path(tmp))
            self.assertEqual(settings.os, "Linux")
            self.assertIsNone(settings.compiler)
            self.assertIsNone(settings.compiler_recipe)

    def test_resolve_settings_applies_provider_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_stub_toolchain(root, "clang", "clang", default=True)
            settings = resolve_settings(BuildProfile(target_os="Linux"), root)
            self.assertEqual(settings.compiler, "clang")
            self.assertEqual(settings.compiler_recipe, "clang")
            self.assertEqual(settings.compiler_cxx_standard, "17")

    def test_android_selects_ndk_from_real_recipes(self):
        self.assertEqual(
            select_toolchain(BuildProfile(target_os="Android", target_arch="ARM"), REAL_RECIPES),
            "android-ndk")

    def test_android_settings_from_real_recipes(self):
        settings = resolve_settings(BuildProfile(target_os="Android", target_arch="ARM"), REAL_RECIPES)
        self.assertEqual(settings.compiler, "clang")
        self.assertEqual(settings.compiler_recipe, "android-ndk")
        self.assertEqual(settings.compiler_libcxx, "c++_static")
        self.assertEqual(settings.os_api_level, "24")


class InjectionTests(unittest.TestCase):
    def test_provider_injected_as_host_require(self):
        recipe = _make_recipe(
            name="zlib", settings=_settings(os="Windows", compiler_recipe="clang"))
        _inject_toolchain_requires(recipe)
        self.assertEqual([(str(r.name), r.build) for r in recipe._requires], [("clang", False)])

    def test_toolchain_layer_recipes_are_skipped(self):
        profile = BuildProfile(target_os="Windows")
        layer = toolchain_layer(REAL_RECIPES, "clang", profile)
        self.assertIn("clang", layer)
        self.assertIn("llvm", layer)
        self.assertIn("msvc", layer)
        self.assertIn("windows-sdk", layer)
        for name in ("llvm", "msvc", "windows-sdk"):
            recipe = _make_recipe(name=name, settings=_settings(os="Windows", compiler_recipe="clang"))
            _inject_toolchain_requires(recipe)
            self.assertEqual(recipe._requires, [], name)

    def test_marked_provider_classes_are_skipped(self):
        layer = toolchain_layer(REAL_RECIPES, "clang", BuildProfile(target_os="Windows"))
        self.assertIn("gcc", layer)
        self.assertIn("android-ndk", layer)

    def test_existing_require_not_duplicated(self):
        recipe = _make_recipe(name="zlib", settings=_settings(os="Windows", compiler_recipe="clang"))
        recipe.requires("clang")
        _inject_toolchain_requires(recipe)
        self.assertEqual(len(recipe._requires), 1)

    def test_no_provider_no_injection(self):
        recipe = _make_recipe(name="zlib", settings=_settings())
        _inject_toolchain_requires(recipe)
        self.assertEqual(recipe._requires, [])


class FindToolchainTests(unittest.TestCase):
    def test_provider_found_by_name_not_by_any_contract(self):
        clang_tc = ToolchainInfo(family="clang", front_kind="clang")
        msvc_tc = ToolchainInfo(family="msvc", front_kind="msvc")
        recipe = _consumer_with_provider("clang", clang_tc, extra_deps=[("msvc", msvc_tc)])
        self.assertIs(find_toolchain(recipe), clang_tc)

    def test_empty_contract_is_not_a_provider(self):
        recipe = _consumer_with_provider("clang", ToolchainInfo())
        self.assertIsNone(find_toolchain(recipe))

    def test_none_without_provider(self):
        self.assertIsNone(find_toolchain(_make_recipe(settings=_settings())))


class ToolchainInfoTests(unittest.TestCase):
    def test_serialize_round_trip(self):
        tc = ToolchainInfo(
            compilers={"c": "/bin/clang"}, front_kind="clang", family="clang",
            msvc_include_dirs=["/msvc/include"], msbuild_properties={"A": "B"})
        self.assertEqual(ToolchainInfo.deserialize(tc.serialize()), tc)

    def test_info_serialize_round_trip(self):
        info = Info(set_defaults=True)
        info.toolchain.compilers = {"c": "/bin/clang"}
        info.toolchain.front_kind = "clang"
        info.redistributable = False
        restored = Info(set_defaults=True).deserialize(info.serialize())
        self.assertEqual(restored.toolchain, info.toolchain)
        self.assertFalse(restored.redistributable)
        empty = Info(set_defaults=True).deserialize(Info(set_defaults=True).serialize())
        self.assertFalse(empty.toolchain)
        self.assertTrue(empty.redistributable)

    def test_merge_first_defined_wins(self):
        tc = ToolchainInfo(front_kind="clang")
        tc.merge(ToolchainInfo(front_kind="msvc", ar="/bin/llvm-ar"))
        self.assertEqual(tc.front_kind, "clang")
        self.assertEqual(tc.ar, "/bin/llvm-ar")

    def test_set_relative_base_folder(self):
        import os
        tc = ToolchainInfo(compilers={"c": "bin/clang"}, sysroot="sysroot", msvc_lib_dirs=["lib/x64"])
        tc.set_relative_base_folder("/pkg")
        self.assertEqual(tc.compilers["c"], os.path.join("/pkg", "bin/clang"))
        self.assertEqual(tc.sysroot, os.path.join("/pkg", "sysroot"))
        self.assertEqual(tc.msvc_lib_dirs, [os.path.join("/pkg", "lib/x64")])


class LTOFlagsTests(unittest.TestCase):
    def _linux_clang_consumer(self, build_type="Release", conf=None):
        tc = ToolchainInfo(family="clang", front_kind="clang")
        settings = _settings(
            os="Linux", build_type=build_type, compiler="clang", compiler_recipe="clang")
        recipe = _consumer_with_provider("clang", tc, settings=settings)
        if conf is not None:
            recipe._state.conf = conf
        return recipe

    def test_default_on_for_linux_clang_release(self):
        self.assertEqual(
            lto_flags(self._linux_clang_consumer()), ["-flto=thin", "-ffat-lto-objects"])

    def test_off_for_debug(self):
        self.assertEqual(lto_flags(self._linux_clang_consumer(build_type="Debug")), [])

    def test_conf_opt_out(self):
        conf = Conf()
        conf.tools.build.lto = False
        self.assertEqual(lto_flags(self._linux_clang_consumer(conf=conf)), [])

    def test_off_outside_linux(self):
        tc = ToolchainInfo(family="clang", front_kind="clang")
        settings = _settings(os="Windows", compiler="clang", compiler_recipe="clang")
        recipe = _consumer_with_provider("clang", tc, settings=settings)
        self.assertEqual(lto_flags(recipe), [])


class CMakeBlockTests(unittest.TestCase):
    def _render(self, block_cls, recipe):
        return block_cls(recipe, toolchain=None, name="test").get_rendered_content()

    def _windows_clang_contract(self):
        return ToolchainInfo(
            family="clang", front_kind="clang-cl",
            compilers={"c": "C:/llvm/bin/clang-cl.exe"},
            linker="C:/llvm/bin/lld-link.exe", ar="C:/llvm/bin/llvm-lib.exe",
            mt="C:/llvm/bin/llvm-mt.exe", target_triple="x86_64-pc-windows-msvc",
            msvc_include_dirs=["C:/msvc/include", "C:/sdk/include/ucrt"],
            msvc_lib_dirs=["C:/msvc/lib/x64", "C:/sdk/lib/um/x64"])

    def test_toolchain_provider_block_renders_contract(self):
        tc = self._windows_clang_contract()
        settings = _settings(os="Windows", compiler="clang", compiler_recipe="clang")
        recipe = _consumer_with_provider("clang", tc, settings=settings)
        content = self._render(ToolchainProviderBlock, recipe)
        assert content is not None
        self.assertIn('set(CMAKE_LINKER "C:/llvm/bin/lld-link.exe")', content)
        self.assertIn("set(CMAKE_C_COMPILER_TARGET x86_64-pc-windows-msvc)", content)
        # On a Windows build machine the CRT/SDK dirs ride INCLUDE/LIB (buildenv), so the
        # block emits no /imsvc or /libpath: flags (cl.exe would reject /imsvc; recipes that
        # embed CMAKE_*_FLAGS into generated sources would choke on the embedded quotes).
        self.assertNotIn("/imsvc", content)
        self.assertNotIn("/libpath:", content)

    def test_toolchain_provider_block_emits_msvc_dirs_when_cross_from_posix(self):
        tc = self._windows_clang_contract()
        settings = _settings(os="Windows", compiler="clang", compiler_recipe="clang")
        recipe = _consumer_with_provider(
            "clang", tc, settings=settings, settings_build=_settings(os="Linux"))
        content = self._render(ToolchainProviderBlock, recipe)
        assert content is not None
        self.assertIn("/imsvcC:/msvc/include", content)
        self.assertIn("/libpath:C:/msvc/lib/x64", content)
        self.assertLess(content.index("C:/msvc/include"), content.index("C:/sdk/include/ucrt"))

    def test_toolchain_provider_block_skips_delegated_toolchain(self):
        tc = ToolchainInfo(family="clang", cmake_toolchain_file="/ndk/android.toolchain.cmake")
        settings = _settings(os="Android", arch="ARM", compiler="clang", compiler_recipe="android-ndk")
        recipe = _consumer_with_provider("android-ndk", tc, settings=settings)
        self.assertIsNone(ToolchainProviderBlock(recipe, toolchain=None, name="test").context())

    def test_toolchain_provider_block_requires_msvc_dirs_for_windows_clang(self):
        tc = ToolchainInfo(family="clang", front_kind="clang-cl")
        settings = _settings(os="Windows", compiler="clang", compiler_recipe="clang")
        recipe = _consumer_with_provider("clang", tc, settings=settings)
        with self.assertRaisesRegex(RecipeException, "packaged MSVC"):
            ToolchainProviderBlock(recipe, toolchain=None, name="test").context()

    def test_lto_block_renders_for_linux_clang(self):
        tc = ToolchainInfo(family="clang", front_kind="clang")
        settings = _settings(os="Linux", compiler="clang", compiler_recipe="clang")
        recipe = _consumer_with_provider("clang", tc, settings=settings)
        content = self._render(LTOBlock, recipe)
        assert content is not None
        self.assertIn("-flto=thin", content)
        self.assertIn("-ffat-lto-objects", content)
        self.assertIn('RECIPE_EXE_LINKER_FLAGS " -flto=thin"', content)


class MsvsToolsetTests(unittest.TestCase):
    def test_contract_toolset_wins(self):
        tc = ToolchainInfo(family="clang", front_kind="clang-cl", msbuild_toolset="ClangCL")
        settings = _settings(os="Windows", compiler="clang", compiler_recipe="clang",
                             compiler_runtime="dynamic")
        recipe = _consumer_with_provider("clang", tc, settings=settings)
        self.assertEqual(msvs_toolset(recipe), "ClangCL")

    def test_fallback_without_contract(self):
        recipe = _make_recipe(settings=_settings(os="Windows", compiler="msvc", compiler_version="194"))
        self.assertEqual(msvs_toolset(recipe), "v143")


class RedistributableTests(unittest.TestCase):
    def test_toolchain_layer_is_marked_non_redistributable(self):
        from thirdparty._internal.pack.meta import probe_redistributable
        for name in ("clang", "gcc", "msvc", "windows-sdk", "llvm", "msbuild", "linux-sysroot", "android-ndk"):
            self.assertFalse(
                probe_redistributable(REAL_RECIPES, name), f"{name} must never be publishable")
        self.assertTrue(probe_redistributable(REAL_RECIPES, "zlib"))

    def test_gather_meta_blocks_non_redistributable(self):
        from thirdparty._internal.pack.meta import gather_meta
        with self.assertRaisesRegex(RecipeException, "not redistributable"):
            gather_meta(REAL_RECIPES, ROOT / "build", "msvc")

    def test_resolve_names_glob_skips_but_explicit_passes(self):
        from thirdparty._internal.cli._recipes import resolve_names
        globbed = resolve_names(REAL_RECIPES, ["msvc*", "zlib"])
        self.assertNotIn("msvc", globbed)
        self.assertIn("zlib", globbed)
        self.assertIn("msvc", resolve_names(REAL_RECIPES, ["msvc"]))

    def test_discovery_finds_real_providers(self):
        from thirdparty._internal.loader import try_load_recipe_class
        for name in ("clang", "apple-clang", "gcc", "msvc", "android-ndk"):
            cls = try_load_recipe_class(REAL_RECIPES, name)
            self.assertIsNotNone(cls, name)
            assert cls is not None
            self.assertTrue(is_toolchain(cls), name)


if __name__ == "__main__":
    unittest.main()
