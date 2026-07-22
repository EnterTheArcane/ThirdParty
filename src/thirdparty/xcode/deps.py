import jinja2
import os
import re
import textwrap
from typing import Any

from thirdparty._internal.util.files import load, save
from thirdparty.apple.utils import _to_apple_arch
from thirdparty.errors import RecipeException
from thirdparty.recipe import RecipeBase

GLOBAL_XCCONFIG_TEMPLATE = textwrap.dedent(
    """
    // Includes both the toolchain and the dependencies
    // files if they exist

    """)

GLOBAL_XCCONFIG_FILENAME = "recipe_config.xcconfig"


def _format_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name).lower()


def _xcconfig_settings_filename(settings: Any, configuration: Any) -> str:
    arch = settings.arch
    architecture = _to_apple_arch(arch) or arch
    props = [
        ("configuration", configuration), ("architecture", architecture), ("sdk name", settings.os_sdk), ("sdk version", settings.os_sdk_version),
    ]
    name = "".join(f"_{v}" for _, v in props if v is not None and v)
    return _format_name(name)


def _xcconfig_conditional(settings: Any, configuration: Any) -> str:
    sdk_condition = "*"
    arch = settings.arch
    architecture = _to_apple_arch(arch) or arch
    sdk = settings.os_sdk if settings.os != "Mac" else "macosx"
    if sdk:
        sdk_condition = "{}{}".format(sdk, settings.os_sdk_version or "*")

    return f"[config={configuration}][arch={architecture}][sdk={sdk_condition}]"


def _add_includes_to_file_or_create(filename: str, template: str, files_to_include: Any) -> str:
    if os.path.isfile(filename):
        content = load(filename)
    else:
        content = template

    for include in files_to_include:
        if include not in content:
            content = content + f'#include "{include}"\n'

    return content


class XcodeDeps:
    general_name = "recipe_deps.xcconfig"

    _conf_xconfig = textwrap.dedent(
        """
        PACKAGE_ROOT_{{pkg_name}}{{condition}} = {{root}}
        // Compiler options for {{pkg_name}}::{{comp_name}}
        SYSTEM_HEADER_SEARCH_PATHS_{{pkg_name}}_{{comp_name}}{{condition}} = {{include_dirs}}
        GCC_PREPROCESSOR_DEFINITIONS_{{pkg_name}}_{{comp_name}}{{condition}} = {{definitions}}
        OTHER_CFLAGS_{{pkg_name}}_{{comp_name}}{{condition}} = {{c_compiler_flags}}
        OTHER_CPLUSPLUSFLAGS_{{pkg_name}}_{{comp_name}}{{condition}} = {{cxx_compiler_flags}}
        FRAMEWORK_SEARCH_PATHS_{{pkg_name}}_{{comp_name}}{{condition}} = {{frameworkdirs}}

        // Link options for {{pkg_name}}::{{comp_name}}
        LIBRARY_SEARCH_PATHS_{{pkg_name}}_{{comp_name}}{{condition}} = {{lib_dirs}}
        OTHER_LDFLAGS_{{pkg_name}}_{{comp_name}}{{condition}} = {{linker_flags}} {{libs}} {{system_libs}} {{frameworks}}
        """)

    _dep_xconfig = textwrap.dedent(
        """
        // Recipe XcodeDeps generated file for {{pkg_name}}::{{comp_name}}
        // Includes all configurations for each dependency
        {% for include in deps_includes %}
        #include "{{include}}"
        {% endfor %}
        #include "{{dep_xconfig_filename}}"

        SYSTEM_HEADER_SEARCH_PATHS = $(inherited) $(SYSTEM_HEADER_SEARCH_PATHS_{{pkg_name}}_{{comp_name}})
        GCC_PREPROCESSOR_DEFINITIONS = $(inherited) $(GCC_PREPROCESSOR_DEFINITIONS_{{pkg_name}}_{{comp_name}})
        OTHER_CFLAGS = $(inherited) $(OTHER_CFLAGS_{{pkg_name}}_{{comp_name}})
        OTHER_CPLUSPLUSFLAGS = $(inherited) $(OTHER_CPLUSPLUSFLAGS_{{pkg_name}}_{{comp_name}})
        FRAMEWORK_SEARCH_PATHS = $(inherited) $(FRAMEWORK_SEARCH_PATHS_{{pkg_name}}_{{comp_name}})

        // Link options for {{pkg_name}}_{{comp_name}}
        LIBRARY_SEARCH_PATHS = $(inherited) $(LIBRARY_SEARCH_PATHS_{{pkg_name}}_{{comp_name}})
        OTHER_LDFLAGS = $(inherited) $(OTHER_LDFLAGS_{{pkg_name}}_{{comp_name}})
        """)

    _all_xconfig = textwrap.dedent(
        """
        // Recipe XcodeDeps generated file
        // Includes all direct dependencies
        """)

    _pkg_xconfig = textwrap.dedent(
        """
        // Recipe XcodeDeps generated file
        // Includes all components for the package
        """)

    def __init__(self, recipe: RecipeBase):
        self._recipe = recipe
        self.configuration = recipe.settings.build_type
        arch = recipe.settings.arch
        self.architecture = _to_apple_arch(arch, default=arch)
        self.os_version = recipe.settings.os_version
        self.sdk = recipe.settings.os_sdk
        self.sdk_version = recipe.settings.os_sdk_version

    def generate(self):
        if self.configuration is None:  # pyright: ignore[reportUnnecessaryComparison]  # defensive invariant check
            raise RecipeException("XcodeDeps.configuration is None, it should have a value")
        if self.architecture is None:
            raise RecipeException("XcodeDeps.architecture is None, it should have a value")
        generator_files = self._content()
        for generator_file, content in generator_files.items():
            save(generator_file, content)

    def _conf_xconfig_file(
        self,
        require: Any,
        pkg_name: str,
        comp_name: str,
        package_folder: str,
        transitive_cpp_infos: Any) -> str:
        """
        content for recipe_poco_x86_release.xcconfig, containing the activation
        """

        def _merged_vars(name: str) -> list[Any]:
            merged = [var for info in transitive_cpp_infos for var in getattr(info, name)]
            return list(dict.fromkeys(merged).keys())

        # TODO: Investigate if paths can be made relative to "root" folder
        fields = {
            "pkg_name": pkg_name,
            "comp_name": comp_name,
            "root": package_folder,
            "include_dirs": " ".join(f'"{p}"' for p in _merged_vars("includedirs")),
            "lib_dirs": " ".join(f'"{p}"' for p in _merged_vars("libdirs")),
            "libs": " ".join(f"-l{lib}" for lib in _merged_vars("libs")),
            "system_libs": " ".join(f"-l{sys_lib}" for sys_lib in _merged_vars("system_libs")),
            "frameworkdirs": " ".join(f'"{p}"' for p in _merged_vars("frameworkdirs")),
            "frameworks": " ".join(f"-framework {framework}" for framework in _merged_vars("frameworks")),
            "definitions": " ".join('"{}"'.format(p.replace('"', '\\"')) for p in _merged_vars("defines")),
            "c_compiler_flags": " ".join('"{}"'.format(p.replace('"', '\\"')) for p in _merged_vars("cflags")),
            "cxx_compiler_flags": " ".join('"{}"'.format(p.replace('"', '\\"')) for p in _merged_vars("cxxflags")),
            "linker_flags": " ".join('"{}"'.format(p.replace('"', '\\"')) for p in _merged_vars("sharedlinkflags")),
            "exe_flags": " ".join('"{}"'.format(p.replace('"', '\\"')) for p in _merged_vars("exelinkflags")),
            "condition": _xcconfig_conditional(self._recipe.settings, self.configuration),
        }

        if not require.headers:
            fields["include_dirs"] = ""

        if not require.libs:
            fields["lib_dirs"] = ""
            fields["libs"] = ""
            fields["system_libs"] = ""
            fields["frameworkdirs"] = ""
            fields["frameworks"] = ""

        if not require.libs and not require.headers:
            fields["definitions"] = ""
            fields["c_compiler_flags"] = ""
            fields["cxx_compiler_flags"] = ""
            fields["linker_flags"] = ""
            fields["exe_flags"] = ""

        template = jinja2.Template(self._conf_xconfig)
        content_multi = template.render(**fields)
        return content_multi

    def _dep_xconfig_file(
        self,
        pkg_name: str,
        comp_name: str,
        name_general: str,
        dep_xconfig_filename: str,
        reqs: Any) -> str:
        # Current directory is the generators_folder
        multi_path = name_general
        if os.path.isfile(multi_path):
            content_multi = load(multi_path)
        else:
            content_multi = self._dep_xconfig

            def _get_includes(components: Any) -> list[str]:
                # if we require the root component dep::dep include recipe_dep.xcconfig
                # for components (dep::component) include recipe_dep_component.xcconfig
                return [f"recipe_{_format_name(component[0])}.xcconfig" if component[0] == component[1] else f"recipe_{_format_name(component[0])}_{_format_name(component[1])}.xcconfig" for component in components]

            content_multi = jinja2.Template(content_multi).render(
                {
                    "pkg_name": pkg_name, "comp_name": comp_name, "dep_xconfig_filename": dep_xconfig_filename, "deps_includes": _get_includes(reqs),
                })

        if dep_xconfig_filename not in content_multi:
            content_multi = content_multi.replace(
                '.xcconfig"', f'.xcconfig"\n#include "{dep_xconfig_filename}"', 1)

        return content_multi

    def _all_xconfig_file(self, deps: Any, content: Any) -> str:
        """
        this is a .xcconfig file including all declared dependencies
        """
        content_multi = content or self._all_xconfig

        for dep in deps.values():
            include_file = f"recipe_{_format_name(dep.name)}.xcconfig"
            if include_file not in content_multi:
                content_multi = content_multi + f'\n#include "{include_file}"\n'
        return content_multi

    def _pkg_xconfig_file(self, components: Any) -> str:
        """
        this is a .xcconfig file including the components for each package
        """
        content_multi = self._pkg_xconfig
        for pkg_name, comp_name in components:
            content_multi = content_multi + f'\n#include "recipe_{pkg_name}_{comp_name}.xcconfig"\n'
        return content_multi

    @property
    def _global_xconfig_content(self) -> str:
        return _add_includes_to_file_or_create(
            GLOBAL_XCCONFIG_FILENAME, GLOBAL_XCCONFIG_TEMPLATE, [self.general_name])

    def _get_content_for_component(
        self,
        require: Any,
        pkg_name: str,
        component_name: str,
        package_folder: str,
        transitive_cpp_infos: Any) -> dict[str, str]:
        result: dict[str, str] = {}

        conf_name = _xcconfig_settings_filename(self._recipe.settings, self.configuration)

        props_name = f"recipe_{pkg_name}_{component_name}{conf_name}.xcconfig"
        result[props_name] = self._conf_xconfig_file(require, pkg_name, component_name, package_folder, transitive_cpp_infos)

        # The entry point for each package
        file_dep_name = f"recipe_{pkg_name}_{component_name}.xcconfig"
        dep_content = self._dep_xconfig_file(pkg_name, component_name, file_dep_name, props_name, [])

        result[file_dep_name] = dep_content
        return result

    @staticmethod
    def _collect_all_transitive(
        info: Any,
        pkg_dep: Any,
        all_deps: Any,
        collected: Any,
        visited: set[int] | None = None):
        """Recursively collect all transitive Info objects (internal and external)
        into a flat list.

        :param info: current Info being processed (root or component)
        :param pkg_dep: dependency object owning the info
        :param all_deps: dict {ref.name: dep} of all available host deps
        :param collected: output list accumulating the Info objects
        :param visited: set of id(info) already processed (created automatically)
        """
        if visited is None:
            visited = set()

        key = id(info)
        if key in visited:
            return
        visited.add(key)
        collected.append(info)

        if info.requires:
            for req in info.requires:
                if "::" not in req:
                    # Internal component from the same package
                    XcodeDeps._collect_all_transitive(
                        pkg_dep.info.components.get(req), pkg_dep, all_deps, collected, visited)
                else:
                    XcodeDeps._resolve_external(req, all_deps, collected, visited)
        elif not pkg_dep.info.has_components:
            for _, d in pkg_dep.dependencies.direct_host.items():
                XcodeDeps._resolve_external(
                    f"{d.name}::{d.name}", all_deps, collected, visited)

    @staticmethod
    def _resolve_external(
        req: str,
        all_deps: Any,
        collected: Any,
        visited: Any):
        """Resolve and follow an external requirement (pkg::comp)."""

        ext_pkg, ext_comp = req.split("::", 1)
        ext_dep = all_deps.get(ext_pkg)
        if ext_dep is None:  # skipped or not visible dependency
            return

        if not ext_dep.info.has_components:
            # Package without components: use root info directly
            XcodeDeps._collect_all_transitive(
                ext_dep.info, ext_dep, all_deps, collected, visited)
        elif ext_pkg == ext_comp:
            # Dependency on the whole package (pkg::pkg): collect all its components
            for comp in ext_dep.info.get_sorted_components().values():
                XcodeDeps._collect_all_transitive(
                    comp, ext_dep, all_deps, collected, visited)
        else:
            # Dependency on a specific component (pkg::comp)
            XcodeDeps._collect_all_transitive(
                ext_dep.info.components.get(ext_comp), ext_dep, all_deps, collected, visited)

    def _content(self) -> dict[str, str]:
        result: dict[str, str] = {}

        # Generate the config files for each component with name recipe_pkgname_compname.xcconfig
        # If a package has no components the name is recipe_pkgname_pkgname.xcconfig
        # All components are included in the recipe_pkgname.xcconfig file
        host_req = self._recipe.dependencies.host
        all_deps = {dep.name: dep for _, dep in host_req.items()}

        direct_deps = self._recipe.dependencies.filter(
            {
                "direct": True, "build": False, "skip": False,
            })
        for require, dep in direct_deps.items():

            dep_name = _format_name(dep.name)

            include_components_names: list[tuple[str, str]] = []
            if dep.info.has_components:

                sorted_components = dep.info.get_sorted_components().items()
                for comp_name, comp_cpp_info in sorted_components:
                    comp_name = _format_name(comp_name)

                    transitive_cpp_infos = []
                    self._collect_all_transitive(
                        comp_cpp_info, dep, all_deps, transitive_cpp_infos)

                    # In case dep is editable and package_folder=None
                    pkg_folder = (
                        dep.folders.package
                        if dep.folders.base_package is not None
                        else dep.folders.recipe
                    )
                    component_content = self._get_content_for_component(
                        require, dep_name, comp_name, pkg_folder, transitive_cpp_infos)
                    include_components_names.append((dep_name, comp_name))
                    result.update(component_content)
            else:
                transitive_cpp_infos = []
                self._collect_all_transitive(
                    dep.info, dep, all_deps, transitive_cpp_infos)
                # In case dep is editable and package_folder=None
                pkg_folder = (
                    dep.folders.package
                    if dep.folders.base_package is not None
                    else dep.folders.recipe
                )
                root_content = self._get_content_for_component(
                    require, dep_name, dep_name, pkg_folder, transitive_cpp_infos)
                include_components_names.append((dep_name, dep_name))
                result.update(root_content)

            result[f"recipe_{dep_name}.xcconfig"] = self._pkg_xconfig_file(include_components_names)

        all_file_content = ""

        # Include direct requires
        direct_deps = self._recipe.dependencies.filter({"direct": True, "build": False, "skip": False})
        result[self.general_name] = self._all_xconfig_file(direct_deps, all_file_content)

        result[GLOBAL_XCCONFIG_FILENAME] = self._global_xconfig_content

        return result
