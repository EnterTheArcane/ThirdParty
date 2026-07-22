import jinja2
import os
import textwrap
from typing import Any, cast

from thirdparty._internal.util.files import save
from thirdparty.apple.utils import is_apple_os, apple_min_version_flag, resolve_apple_flags, apple_extra_flags
from thirdparty.build.cross_building import cross_building, can_run
from thirdparty.build.flags import (
    architecture_link_flag, libcxx_flags, architecture_flag, threads_flags, )
from thirdparty.env import VirtualBuildEnv
from thirdparty.errors import RecipeException
from thirdparty.meson.helpers import get_apple_subsystem, to_cppstd_flag, to_cstd_flag, to_meson_machine, to_meson_value
from thirdparty.microsoft import VCVars, msvc_runtime_flag
from thirdparty.recipe import RecipeBase


class MesonToolchain:
    """
    MesonToolchain generator
    """
    native_filename = "recipe_meson_native.ini"
    cross_filename = "recipe_meson_cross.ini"

    _meson_file_template = textwrap.dedent(
        """
        [properties]
        {% for it, value in properties.items() -%}
        {{it}} = {{value}}
        {% endfor %}
    
        [constants]
        preprocessor_definitions = [{% for it, value in preprocessor_definitions.items() -%}
        '-D{{ it }}="{{ value}}"'{%- if not loop.last %}, {% endif %}{% endfor %}]
    
        [project options]
        {% for it, value in project_options.items() -%}
        {{it}} = {{value}}
        {% endfor %}
    
        {% for subproject, listkeypair in subproject_options -%}
        [{{subproject}}:project options]
        {% for keypair in listkeypair -%}
        {% for it, value in keypair.items() -%}
        {{it}} = {{value}}
        {% endfor %}
        {% endfor %}
        {% endfor %}
    
        [binaries]
        {% for it, value in binaries.items() -%}
        {{it}} = {{value}}
        {% endfor %}
    
        [built-in options]
        {% if buildtype %}
        buildtype = '{{buildtype}}'
        {% endif %}
        {% if default_library %}
        default_library = '{{default_library}}'
        {% endif %}
        {% if b_vscrt %}
        b_vscrt = '{{b_vscrt}}'
        {% endif %}
        {% if b_ndebug %}
        b_ndebug = {{b_ndebug}}
        {% endif %}
        {% if b_staticpic %}
        b_staticpic = {{b_staticpic}}
        {% endif %}
        {% if cpp_std %}
        cpp_std = '{{cpp_std}}'
        {% endif %}
        {% if c_std %}
        c_std = '{{c_std}}'
        {% endif %}
        {% if backend %}
        backend = '{{backend}}'
        {% endif %}
        {% if pkg_config_path %}
        pkg_config_path = '{{pkg_config_path}}'
        {% endif %}
        {% if build_pkg_config_path %}
        build.pkg_config_path = '{{build_pkg_config_path}}'
        {% endif %}
        # C/C++ arguments
        c_args = {{c_args}} + preprocessor_definitions
        c_link_args = {{c_link_args}}
        cpp_args = {{cpp_args}} + preprocessor_definitions
        cpp_link_args = {{cpp_link_args}}
        {% if is_apple_system %}
        # Objective-C/C++ arguments
        objc_args = {{objc_args}} + preprocessor_definitions
        objc_link_args = {{objc_link_args}}
        objcpp_args = {{objcpp_args}} + preprocessor_definitions
        objcpp_link_args = {{objcpp_link_args}}
        {% endif %}
    
        {% for context, values in cross_build.items() %}
        [{{context}}_machine]
        system = '{{values["system"]}}'
        {% if values.get("subsystem") %}
        subsystem = '{{values["subsystem"]}}'
        {% endif %}
        cpu_family = '{{values["cpu_family"]}}'
        cpu = '{{values["cpu"]}}'
        endian = '{{values["endian"]}}'
        {% endfor %}
        """)
    
    project_options: dict[str, Any]

    def __init__(
        self,
        recipe: RecipeBase,
        backend: str | None = None,
        native: bool = False):
        """
        :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
        :param backend: (**DEPRECATED**, use ``self.backend`` instead) ``str`` ``backend`` Meson variable
                        value. By default, ``ninja``.
        :param native: ``bool`` Indicates whether you want Recipe to create the
                       ``recipe_meson_native.ini`` in a cross-building context. Notice that it only
                       makes sense if your project's ``meson.build`` uses the ``native=true``
                       (see also https://mesonbuild.com/Cross-compilation.html#mixing-host-and-build-targets).
        """
        self._recipe = recipe
        self._native = native
        self._is_apple_system = is_apple_os(self._recipe)
        is_cross_building = cross_building(recipe)  # x86_64->x86 is considered cross-building
        if not is_cross_building and native:
            raise RecipeException(
                "You can only pass native=True if you're cross-building, "
                "otherwise, it could cause unexpected results.")
        self._recipe_conf = self._recipe.conf
        # Values are kept as Python built-ins so users can modify them more easily, and they are
        # only converted to Meson file syntax for rendering
        # priority: first user conf, then recipe, last one is default "ninja"
        self.backend = backend or "ninja"
        build_type = self._recipe.settings.build_type
        #: Build type to use.
        self.buildtype = {
            "Debug": "debug",  # Note, it is not "'debug'"
            "Release": "release", "MinSizeRel": "minsize", "RelWithDebInfo": "debugoptimized",
        }.get(build_type, build_type)
        #: Disable asserts.
        self.b_ndebug = "true" if self.buildtype != "debug" else "false"

        # https://mesonbuild.com/Builtin-options.html#base-options
        pic = self._recipe.options.get_safe("pic")
        shared = self._recipe.options.get_safe("shared") is True
        static = self._recipe.options.get_safe("shared") is False
        #: Build static libraries as position independent. By default, ``self.options.get_safe("pic")``
        self.b_staticpic = pic if (static and pic is not None) else None
        # https://mesonbuild.com/Builtin-options.html#core-options
        # Do not adjust "debug" if already adjusted "buildtype"
        #: Default library type, e.g., "shared.
        self.default_library = ("shared" if shared else "static") if shared or static else None
        
        if self._recipe.settings.os == "Windows" and "pic" in self._recipe.options:
            self._recipe.options.pic = False

        compiler = self._recipe.settings.compiler
        if compiler is None:
            raise RecipeException("MesonToolchain needs 'settings.compiler', but it is not defined")
        compiler_version = self._recipe.settings.compiler_version
        if compiler_version is None:
            raise RecipeException("MesonToolchain needs 'settings.compiler_version', but it is not defined")

        cppstd = self._recipe.settings.compiler_cxx_standard
        cstd = self._recipe.settings.compiler_c_standard
        #: C++ language standard to use. Defined by ``to_cppstd_flag()`` by default.
        self.cpp_std = to_cppstd_flag(self._recipe, compiler, compiler_version, cppstd)
        #: C language standard to use. Defined by ``to_cstd_flag()`` by default.
        self.c_std = to_cstd_flag(self._recipe, cstd)
        #: VS runtime library to use. Defined by ``msvc_runtime_flag()`` by default.
        self.b_vscrt = None
        if compiler in ("msvc", "clang"):
            vscrt = msvc_runtime_flag(self._recipe)
            if vscrt:
                self.b_vscrt = str(vscrt).lower()

        # Extra flags
        #: List of extra ``CXX`` flags. Added to ``cpp_args``
        self.extra_cxxflags: list[str] = []
        #: List of extra ``C`` flags. Added to ``c_args``
        self.extra_cflags: list[str] = []
        #: List of extra linker flags. Added to ``c_link_args`` and ``cpp_link_args``
        self.extra_ldflags: list[str] = []
        #: List of extra preprocessor definitions. Added to ``c_args`` and ``cpp_args`` with the
        #: format ``-D[FLAG_N]``.
        self.extra_defines: list[str] = []
        #: Architecture flag deduced by Recipe and added to ``c_args``, ``cpp_args``, ``c_link_args`` and ``cpp_link_args``
        self.arch_flag = architecture_flag(self._recipe)  # upstream issue 17624
        #: Architecture link flag deduced by Recipe and added to ``c_link_args`` and ``cpp_link_args``
        self.arch_link_flag = architecture_link_flag(self._recipe)
        #: Threads flags deduced by Recipe and added to ``c_args``, ``cpp_args``, ``c_link_args`` and ``cpp_link_args``
        self.threads_flags = threads_flags(self._recipe)
        #: Dict-like object that defines Meson ``properties`` with ``key=value`` format
        self.properties: dict[str, Any] = {}
        #: Dict-like object that defines Meson ``binaries`` with ``key=value`` format. If any dict key
        #: matches a public attribute binary name, e.g., "c", "cpp", etc., it will override that one.
        self.binaries: dict[str, Any] = {}
        #: Dict-like object that defines Meson ``project options`` with ``key=value`` format
        self.project_options = {
            "wrap_mode": "nofallback",  # upstream issue 10671
        }
        if not self._recipe.conf.tools.compilation.verbose:
            # Quiet: meson's default warning_level (1) injects /W2 (msvc) / -Wall, which conflicts
            # with the framework's injected -w -> "D9025: overriding '/w' with '/W2'" per file.
            # Level 0 emits no warning flags, so -w cleanly wins and warnings stay suppressed.
            self.project_options["warning_level"] = "0"
        #: Dict-like object that defines Meson ``preprocessor definitions``
        self.preprocessor_definitions: dict[str, Any] = {}
        # Add all the default dirs
        self.project_options.update(self._get_default_dirs())
        #: Dict-like object that defines Meson ``subproject options``.
        self.subproject_options: dict[str, Any] = {}
        #: Defines the Meson ``pkg_config_path`` variable
        self.pkg_config_path = self._recipe.folders.generators
        #: Defines the Meson ``build.pkg_config_path`` variable (build context)
        # Issue: upstream issue 12342
        # Issue: upstream issue 14935
        self.build_pkg_config_path = None
        self.libcxx, self.gcc_cxx11_abi = libcxx_flags(self._recipe)
        #: Dict-like object with the build, host, and target as the Meson machine context
        self.cross_build: dict[str, dict[str, Any]] = {}
        default_comp = ""
        default_comp_cpp = ""
        if native is False and is_cross_building:
            os_host = recipe.settings.os
            arch_host = recipe.settings.arch
            os_build = recipe.settings_build.os
            arch_build = recipe.settings_build.arch
            self.cross_build["build"] = to_meson_machine(os_build, arch_build)
            self.cross_build["host"] = to_meson_machine(os_host, arch_host)
            # Check subsystem if it's Apple cross-building only. It requires Meson >= 1.2.0,
            # but it does not break lower versions.
            # See https://mesonbuild.com/Reference-tables.html#subsystem-names-since-120
            # Issue: upstream issue 17873
            if self._is_apple_system and is_apple_os(recipe, build_context=True):
                sdk_build = recipe.settings_build.os_sdk
                sdk_host = recipe.settings.os_sdk
                self.cross_build["host"]["subsystem"] = get_apple_subsystem(sdk_host)
                self.cross_build["build"]["subsystem"] = get_apple_subsystem(sdk_build)
            # Issue: upstream issue 19217
            self.properties["needs_exe_wrapper"] = not can_run(self._recipe)
            if is_apple_os(self._recipe):  # default cross-compiler in Apple is common
                default_comp = "clang"
                default_comp_cpp = "clang++"
        else:
            if "clang" in compiler:
                default_comp = "clang"
                default_comp_cpp = "clang++"
            elif compiler == "gcc":
                default_comp = "gcc"
                default_comp_cpp = "g++"

        if "Visual" in compiler or compiler == "msvc":
            default_comp = "cl"
            default_comp_cpp = "cl"

        # Read configuration for sys_root property (honoring existing conf)
        self._sys_root = self._recipe_conf.tools.build.sysroot

        # Read configuration for compilers
        compilers_by_conf = self._recipe_conf.tools.build.compiler_executables
        # Read the VirtualBuildEnv to update the variables
        build_env: dict[str, Any] = cast(
            "dict[str, Any]",
            self._recipe.buildenv_build.vars(self._recipe)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            if native
            else VirtualBuildEnv(self._recipe).vars())
        #: Sets the Meson ``c`` variable, defaulting to the ``CC`` build environment value.
        #: If provided as a blank-separated string, it will be transformed into a list.
        #: Otherwise, it remains a single string.
        self.c = compilers_by_conf.get("c") or self._sanitize_env_format(build_env.get("CC")) or default_comp
        #: Sets the Meson ``cpp`` variable, defaulting to the ``CXX`` build environment value.
        #: If provided as a blank-separated string, it will be transformed into a list.
        #: Otherwise, it remains a single string.
        self.cpp = compilers_by_conf.get("cpp") or self._sanitize_env_format(build_env.get("CXX")) or default_comp_cpp
        #: Sets the Meson ``ld`` variable, defaulting to the ``LD`` build environment value.
        #: If provided as a blank-separated string, it will be transformed into a list.
        #: Otherwise, it remains a single string.
        self.ld = self._sanitize_env_format(build_env.get("LD"))
        # FIXME: Should we use the new tools.build:compiler_executables and avoid buildenv?
        # Issue related: https://github.com/mesonbuild/meson/issues/6442
        # PR related: https://github.com/mesonbuild/meson/pull/6457
        #: Defines the Meson ``c_ld`` variable. Defaulted to ``CC_LD``
        #: environment value
        self.c_ld = build_env.get("CC_LD")
        #: Defines the Meson ``cpp_ld`` variable. Defaulted to ``CXX_LD``
        #: environment value
        self.cpp_ld = build_env.get("CXX_LD")
        #: Defines the Meson ``ar`` variable. Defaulted to ``AR`` build environment value
        self.ar = build_env.get("AR")
        #: Defines the Meson ``strip`` variable. Defaulted to ``STRIP`` build environment value
        self.strip = build_env.get("STRIP")
        #: Defines the Meson ``as`` variable. Defaulted to ``AS`` build environment value
        self.as_ = build_env.get("AS")
        #: Defines the Meson ``windres`` variable. Defaulted to ``WINDRES`` build environment value
        self.windres = build_env.get("WINDRES")
        #: Defines the Meson ``pkgconfig`` variable. Defaulted to ``PKG_CONFIG``
        #: build environment value
        self.pkgconfig = (self._recipe_conf.tools.gnu.pkg_config or build_env.get("PKG_CONFIG"))
        #: Defines the Meson ``c_args`` variable. Defaulted to ``CFLAGS`` build environment value
        self.c_args = self._get_env_list(build_env.get("CFLAGS", []))
        #: Defines the Meson ``c_link_args`` variable. Defaulted to ``LDFLAGS`` build
        #: environment value
        self.c_link_args = self._get_env_list(build_env.get("LDFLAGS", []))
        #: Defines the Meson ``cpp_args`` variable. Defaulted to ``CXXFLAGS`` build environment value
        self.cpp_args = self._get_env_list(build_env.get("CXXFLAGS", []))
        #: Defines the Meson ``cpp_link_args`` variable. Defaulted to ``LDFLAGS`` build
        #: environment value
        self.cpp_link_args = self._get_env_list(build_env.get("LDFLAGS", []))

        # Apple flags and variables
        #: Apple arch flag as a list, e.g., ``["-arch", "i386"]``
        self.apple_arch_flag: list[str] = []
        #: Apple sysroot flag as a list, e.g., ``["-isysroot", "./Platforms/MacOSX.platform"]``
        self.apple_isysroot_flag: list[str] = []
        #: Apple minimum binary version flag as a list, e.g., ``["-mios-version-min", "10.8"]``
        self.apple_min_version_flag: list[Any] = []
        #: Apple bitcode, visibility and arc flags
        self.apple_extra_flags = apple_extra_flags(self._recipe)
        #: Defines the Meson ``objc`` variable. Defaulted to ``None``, if if any Apple OS ``clang``
        self.objc = None
        #: Defines the Meson ``objcpp`` variable. Defaulted to ``None``, if if any Apple OS ``clang++``
        self.objcpp = None
        #: Defines the Meson ``objc_args`` variable. Defaulted to ``OBJCFLAGS`` build environment value
        self.objc_args: list[Any] = []
        #: Defines the Meson ``objc_link_args`` variable. Defaulted to ``LDFLAGS`` build environment value
        self.objc_link_args: list[Any] = []
        #: Defines the Meson ``objcpp_args`` variable. Defaulted to ``OBJCXXFLAGS`` build environment value
        self.objcpp_args: list[Any] = []
        #: Defines the Meson ``objcpp_link_args`` variable. Defaulted to ``LDFLAGS`` build environment value
        self.objcpp_link_args: list[Any] = []

        self._resolve_apple_flags_and_variables(build_env, compilers_by_conf)
        if not native:
            self._resolve_android_cross_compilation()

    def _get_default_dirs(self) -> dict[str, Any]:
        """
        Get all the default directories from cpp.package.

        Issues related:
            - upstream issue 9713
            - upstream issue 11596
        """

        def _get_cpp_info_value(name: str) -> Any:
            elements = getattr(self._recipe.info, name)
            return elements[0] if elements else None

        ret: dict[str, Any] = {}
        bindir = _get_cpp_info_value("bindirs")
        datadir = _get_cpp_info_value("resdirs")
        libdir = _get_cpp_info_value("libdirs")
        includedir = _get_cpp_info_value("includedirs")
        if bindir:
            ret.update(
                {
                    "bindir": bindir, "sbindir": bindir, "libexecdir": bindir,
                })
        if datadir:
            ret.update(
                {
                    "datadir": datadir, "localedir": datadir, "mandir": datadir, "infodir": datadir,
                })
        if includedir:
            ret["includedir"] = includedir
        if libdir:
            ret["libdir"] = libdir
        return ret

    def _resolve_apple_flags_and_variables(self, build_env: Any, compilers_by_conf: Any):
        if not self._is_apple_system:
            return
        # Calculating the main Apple flags
        _min_flag, arch_flag, isysroot_flag = (resolve_apple_flags(self._recipe, is_cross_building=bool(self.cross_build)))
        self.apple_arch_flag = arch_flag.split() if arch_flag else []
        self.apple_isysroot_flag = isysroot_flag.split() if isysroot_flag else []
        self.apple_min_version_flag = [apple_min_version_flag(self._recipe)]
        # Objective C/C++ ones
        self.objc = compilers_by_conf.get("objc", "clang")
        self.objcpp = compilers_by_conf.get("objcpp", "clang++")
        enable_arc = self._recipe.conf.tools.apple.enable_arc
        fobj_arc = ""
        if enable_arc:
            fobj_arc = "-fobjc-arc"
        if enable_arc is False:
            fobj_arc = "-fno-objc-arc"
        self.objc_args = self._get_env_list(build_env.get("OBJCFLAGS", [])) + [fobj_arc]
        self.objc_link_args = self._get_env_list(build_env.get("LDFLAGS", []))
        self.objcpp_args = self._get_env_list(build_env.get("OBJCXXFLAGS", [])) + [fobj_arc]
        self.objcpp_link_args = self._get_env_list(build_env.get("LDFLAGS", []))

    def _resolve_android_cross_compilation(self):
        if not self.cross_build or not self.cross_build["host"]["system"] == "android":
            return

        ndk_path = self._recipe_conf.tools.android.ndk_path
        if not ndk_path:
            raise RecipeException(
                "You must provide a NDK path. Use 'tools.android:ndk_path' "
                "configuration field.")

        arch = self._recipe.settings.arch
        os_build = self.cross_build["build"]["system"]
        ndk_bin = os.path.join(
            ndk_path, "toolchains", "llvm", "prebuilt", f"{os_build}-x86_64", "bin")
        android_api_level = self._recipe.settings.os_api_level
        android_target = {
            "ARM": "aarch64-linux-android", "X64": "x86_64-linux-android",
        }.get(arch)
        os_build = self._recipe.settings_build.os
        compile_ext = ".cmd" if os_build == "Windows" else ""
        # User has more prio than Recipe
        self.c = os.path.join(ndk_bin, f"{android_target}{android_api_level}-clang{compile_ext}")
        self.cpp = os.path.join(ndk_bin, f"{android_target}{android_api_level}-clang++{compile_ext}")
        self.ar = os.path.join(ndk_bin, "llvm-ar")

    @property
    def _rpath_link_flag(self) -> list[str]:
        add_rpath_link = self._recipe.conf.tools.build.add_rpath_link
        if not add_rpath_link:
            return []
        runtime_dirs: list[Any] = []
        host_req = self._recipe.dependencies.filter({"build": False}).values()
        for req in host_req:
            cppinfo = req.info.aggregated_components()
            runtime_dirs.extend(cppinfo.libdirs)
        return ["-Wl,-rpath-link=" + ":".join(runtime_dirs)] if runtime_dirs else []

    def _get_extra_flags(self) -> dict[str, Any]:
        # Now, it's time to get all the flags defined by the user
        cxxflags = self._recipe_conf.tools.build.cxxflags
        cflags = self._recipe_conf.tools.build.cflags
        sharedlinkflags = self._recipe_conf.tools.build.sharedlinkflags
        exelinkflags = self._recipe_conf.tools.build.exelinkflags
        linker_scripts = self._recipe_conf.tools.build.linker_scripts
        linker_script_flags = ["-T" + str(linker_script) for linker_script in linker_scripts]
        defines = self._recipe_conf.tools.build.defines
        sys_root = [f"--sysroot={self._sys_root}"] if self._sys_root else [""]
        ld = (sharedlinkflags + exelinkflags + linker_script_flags + sys_root + self.extra_ldflags + self.threads_flags)
        # Apple extra flags from confs (visibilty, bitcode, arc)
        cxxflags += self.apple_extra_flags
        cflags += self.apple_extra_flags
        ld += self.apple_extra_flags
        return {
            "cxxflags": ([self.arch_flag] + cxxflags + sys_root + self.extra_cxxflags + self.threads_flags),
            "cflags": [self.arch_flag] + cflags + sys_root + self.extra_cflags + self.threads_flags,
            "ldflags": [self.arch_flag] + [self.arch_link_flag] + ld + self._rpath_link_flag,
            "defines": [f"-D{d}" for d in (defines + self.extra_defines)],
        }

    @staticmethod
    def _get_env_list(v: Any) -> Any:
        # FIXME: Should Environment have the "check_type=None" keyword as Conf?
        return v.strip().split() if not isinstance(v, list) else cast("list[Any]", v)

    @staticmethod
    def _filter_list_empty_fields(v: Any) -> list[Any]:
        return list(filter(bool, v))

    @staticmethod
    def _sanitize_env_format(value: Any) -> Any:
        if value is None or isinstance(value, list):
            return cast("list[Any] | None", value)
        if not isinstance(value, str):
            raise RecipeException(f"MesonToolchain: Value '{value}' should be a string")
        ret = [x.strip() for x in value.split() if x]
        return ret[0] if len(ret) == 1 else ret

    def _get_binaries(self) -> dict[str, Any]:
        """
        Gets all the binaries elements to fill the [binaries] section
        """
        ret = {
            "c": self.c, "cpp": self.cpp, "ld": self.ld, "c_ld": self.c_ld, "cpp_ld": self.cpp_ld, "ar": self.ar, "strip": self.strip, "as": self.as_, "windres": self.windres, "pkgconfig": self.pkgconfig, "pkg-config": self.pkgconfig,
        }
        if self._is_apple_system:
            ret.update(
                {
                    "objc": self.objc, "objcpp": self.objcpp,
                })
        # Let's give more prio to any value entered by the new binaries attribute
        ret.update(self.binaries)
        return ret

    @property
    def _context(self) -> dict[str, Any]:
        apple_flags = self.apple_isysroot_flag + self.apple_arch_flag + self.apple_min_version_flag
        extra_flags = self._get_extra_flags()

        self.c_args.extend(apple_flags + extra_flags["cflags"] + extra_flags["defines"])
        self.cpp_args.extend(apple_flags + extra_flags["cxxflags"] + extra_flags["defines"])
        self.c_link_args.extend(apple_flags + extra_flags["ldflags"])
        self.cpp_link_args.extend(apple_flags + extra_flags["ldflags"])
        # Objective C/C++
        self.objc_args.extend(self.c_args)
        self.objcpp_args.extend(self.cpp_args)
        # These link_args have already the LDFLAGS env value so let's add only the new possible ones
        self.objc_link_args.extend(self.c_link_args)
        self.objcpp_link_args.extend(self.cpp_link_args)

        if self.preprocessor_definitions:
            self._recipe.output.warning(
                "Use 'extra_defines' attribute for compiler preprocessor definitions instead " + "of 'preprocessor_definitions'", warn_tag="deprecated")

        if self.libcxx:
            self.cpp_args.append(self.libcxx)
            self.cpp_link_args.append(self.libcxx)
        if self.gcc_cxx11_abi:
            self.cpp_args.append(f"-D{self.gcc_cxx11_abi}")

        subproject_options: dict[str, Any] = {}
        for subproject, listkeypair in self.subproject_options.items():
            if listkeypair:
                if not isinstance(listkeypair, list):
                    raise RecipeException("MesonToolchain.subproject_options must be a list of dicts")
                subproject_options[subproject] = [{k: to_meson_value(v) for k, v in keypair.items()} for keypair in cast("list[dict[str, Any]]", listkeypair)]
        return {
            # https://mesonbuild.com/Machine-files.html#properties
            "properties": {k: to_meson_value(v) for k, v in self.properties.items()}, # https://mesonbuild.com/Machine-files.html#project-specific-options
            "project_options": {k: to_meson_value(v) for k, v in self.project_options.items()}, # https://mesonbuild.com/Subprojects.html#build-options-in-subproject
            "subproject_options": subproject_options.items(), # https://mesonbuild.com/Builtin-options.html#directories
            # https://mesonbuild.com/Machine-files.html#binaries
            # https://mesonbuild.com/Reference-tables.html#compiler-and-linker-selection-variables
            "binaries": {k: to_meson_value(v) for k, v in self._get_binaries().items() if v is not None}, # https://mesonbuild.com/Builtin-options.html#core-options
            "buildtype": self.buildtype,
            "default_library": self.default_library,
            "backend": "ninja", # https://mesonbuild.com/Builtin-options.html#base-options
            "b_vscrt": self.b_vscrt,
            "b_staticpic": to_meson_value(self.b_staticpic),  # boolean
            "b_ndebug": to_meson_value(self.b_ndebug),  # boolean as string
            # https://mesonbuild.com/Builtin-options.html#compiler-options
            "cpp_std": self.cpp_std,
            "c_std": self.c_std,
            "c_args": to_meson_value(self._filter_list_empty_fields(self.c_args)),
            "c_link_args": to_meson_value(self._filter_list_empty_fields(self.c_link_args)),
            "cpp_args": to_meson_value(self._filter_list_empty_fields(self.cpp_args)),
            "cpp_link_args": to_meson_value(self._filter_list_empty_fields(self.cpp_link_args)),
            "objc_args": to_meson_value(self._filter_list_empty_fields(self.objc_args)),
            "objc_link_args": to_meson_value(self._filter_list_empty_fields(self.objc_link_args)),
            "objcpp_args": to_meson_value(self._filter_list_empty_fields(self.objcpp_args)),
            "objcpp_link_args": to_meson_value(self._filter_list_empty_fields(self.objcpp_link_args)),
            "pkg_config_path": self.pkg_config_path,
            "build_pkg_config_path": self.build_pkg_config_path, #: Deprecated: Dict-like object that defines Meson ``preprocessor definitions``. Use the extra_defines attribute instead.
            "preprocessor_definitions": self.preprocessor_definitions,
            "cross_build": self.cross_build,
            "is_apple_system": self._is_apple_system,
        }

    @property
    def _filename(self) -> str:
        if self.cross_build and self._native:
            return self.native_filename
        elif self.cross_build:
            return self.cross_filename
        else:
            return self.native_filename

    @property
    def _content(self) -> str:
        """
        Gets content of the file to be used by Meson as its context.

        :return: ``str`` whole Meson context content.
        """
        context = self._context
        content = jinja2.Template(
            self._meson_file_template, trim_blocks=True, lstrip_blocks=True, undefined=jinja2.StrictUndefined).render(context)
        return content

    def generate(self):
        """
        Creates a ``recipe_meson_native.ini`` (if native builds) or a
        ``recipe_meson_cross.ini`` (if cross builds) with the proper content.
        If Windows OS, it will be created a ``vcvars_env.bat`` as well.
        """
        self._recipe.output.info(f"MesonToolchain generated: {self._filename}")
        save(self._filename, self._content)
        # FIXME: Should we check the OS and compiler to call VCVars?
        VCVars(self._recipe).generate()
