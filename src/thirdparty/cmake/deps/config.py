import textwrap

import jinja2

from thirdparty._internal.util.generators import relativize_path
from thirdparty.cmake.utils import parse_extra_variable, cmake_escape_value

from typing import Any
from thirdparty.recipe import RecipeBase


class ConfigTemplate2:
    """
    FooConfig.cmake
    foo-config.cmake
    """

    def __init__(
        self,
        cmakedeps: Any,
        require: Any,
        recipe: RecipeBase,
        full_cpp_info: Any):
        self._cmakedeps = cmakedeps
        self._require = require
        self._recipe = recipe
        self._full_cpp_info = full_cpp_info

    def content(self) -> str:
        t = jinja2.Template(
            self._template, trim_blocks=True, lstrip_blocks=True, undefined=jinja2.StrictUndefined)
        return t.render(self._context)

    @property
    def filename(self) -> str:
        f = self._cmakedeps.get_cmake_filename(self._recipe)
        return f"{f}-config.cmake" if f == f.lower() else f"{f}Config.cmake"

    @property
    def _context(self) -> dict[str, Any]:
        f = self._cmakedeps.get_cmake_filename(self._recipe)
        targets_include = f"{f}Targets.cmake"
        pkg_name = self._recipe.name
        build_modules_paths: list[Any] = self._cmakedeps.get_property(
            "cmake_build_modules", self._recipe, check_type=list) or []
        # FIXME: Proper escaping of paths for CMake and relativization
        # FIXME: build_module_paths coming from last config only
        build_modules_paths = [f.replace("\\", "/") for f in build_modules_paths]
        build_modules_paths = [relativize_path(
            p, self._cmakedeps._recipe, "${CMAKE_CURRENT_LIST_DIR}") for p in build_modules_paths]
        components: Any = self._cmakedeps.get_property(
            "cmake_components", self._recipe, check_type=list)
        if components is None:  # Lets compute the default components names
            components = []
            # This assumes that cmake_components is only defined with not multi .libs=[lib1, lib2]
            for name in self._recipe.info.components:
                if name.startswith("_"):  # Skip private components
                    continue
                comp_components = self._cmakedeps.get_property(
                    "cmake_components", self._recipe, name, check_type=list)
                if comp_components:
                    components.extend(comp_components)
                else:
                    cmakename = self._cmakedeps.get_property(
                        "cmake_target_name", self._recipe, name)
                    if cmakename and "::" in cmakename:  # Remove package namespace
                        cmakename = cmakename.split("::", 1)[1]
                    components.append(cmakename or name)
        components = " ".join(components) if components else ""

        result: dict[str, Any] = {
            "filename": f, "components": components, "pkg_name": pkg_name, "targets_include_file": targets_include, "build_modules_paths": build_modules_paths,
        }

        conf_extra_variables = self._recipe.conf.tools.cmake.toolchain.extra_variables
        dep_extra_variables: dict[Any, Any] = self._cmakedeps.get_property(
            "cmake_extra_variables", self._recipe, check_type=dict) or {}
        # The configuration variables have precedence over the dependency ones
        extra_variables = {dep: value for dep, value in dep_extra_variables.items() if dep not in conf_extra_variables}
        parsed_extra_variables: dict[Any, Any] = {}
        for key, value in extra_variables.items():
            parsed_extra_variables[key] = parse_extra_variable(
                "cmake_extra_variables", key, value)
        result["extra_variables"] = parsed_extra_variables

        result.update(self._get_legacy_vars())
        return result

    def _get_legacy_vars(self) -> dict[str, Any]:
        # Auxiliary variables for legacy consumption and try_compile cases
        pkg_name = self._recipe.name
        prefixes: list[Any] = self._cmakedeps.get_property(
            "cmake_additional_variables_prefixes", self._recipe, check_type=list) or []

        f = self._cmakedeps.get_cmake_filename(self._recipe)
        prefixes = [f] + prefixes
        include_dirs = definitions = libraries = None
        if not self._require.build:  # To add global variables for try_compile and legacy
            aggregated_cppinfo = self._full_cpp_info.aggregated_components()
            # FIXME: Proper escaping of paths for CMake
            incdirs: list[Any] = [i.replace("\\", "/") for i in aggregated_cppinfo.includedirs]
            incdirs = [relativize_path(i, self._cmakedeps._recipe, "${CMAKE_CURRENT_LIST_DIR}") for i in incdirs]
            include_dirs = ";".join(incdirs)
            definitions = ";".join("-D" + cmake_escape_value(d) for d in aggregated_cppinfo.defines)

            libraries: Any = []
            if self._full_cpp_info.has_components:
                for component in self._full_cpp_info.components.keys():
                    root_target_name = self._cmakedeps.get_property(
                        "cmake_target_name", self._recipe, comp_name=component)
                    libraries.append(root_target_name or f"{pkg_name}::{component}")
            else:
                root_target_name = self._cmakedeps.get_property("cmake_target_name", self._recipe)
                libraries.append(root_target_name or f"{pkg_name}::{pkg_name}")
            libraries = " ".join(libraries) if libraries else ""
        return {
            "additional_variables_prefixes": prefixes, "version": self._recipe.version, "include_dirs": include_dirs, "definitions": definitions, "libraries": libraries,
        }

    @property
    def _template(self) -> str:
        return textwrap.dedent(
            """
            # Requires CMake > 3.15
            if(${CMAKE_VERSION} VERSION_LESS "3.15")
                message(FATAL_ERROR "The 'CMakeDeps' generator only works with CMake >= 3.15")
            endif()
    
            include(${CMAKE_CURRENT_LIST_DIR}/{{ targets_include_file }})
    
            get_property(isMultiConfig GLOBAL PROPERTY GENERATOR_IS_MULTI_CONFIG)
            if(NOT isMultiConfig AND NOT CMAKE_BUILD_TYPE)
                message(FATAL_ERROR "Please, set the CMAKE_BUILD_TYPE variable when calling to CMake "
                                    "adding the '-DCMAKE_BUILD_TYPE=<build_type>' argument.")
            endif()
    
            {% if components %}
            set({{filename}}_PACKAGE_PROVIDED_COMPONENTS {{components}})
            foreach(comp {%raw%}${{%endraw%}{{filename}}_FIND_COMPONENTS})
                if(NOT ${comp} IN_LIST {{filename}}_PACKAGE_PROVIDED_COMPONENTS)
                if({%raw%}${{%endraw%}{{filename}}_FIND_REQUIRED_${comp}})
                    message(STATUS "Recipe: Error: '{{pkg_name}}' required COMPONENT '${comp}' not found")
                    set({{filename}}_FOUND FALSE)
                endif()
                endif()
            endforeach()
            {% endif %}
    
            ################# Global variables for try compile and legacy ##############
            {% for prefix in additional_variables_prefixes %}
            set({{ prefix }}_VERSION_STRING "{{ version }}")
            {% if include_dirs is not none %}
            set({{ prefix }}_INCLUDE_DIRS "{{ include_dirs }}" )
            set({{ prefix }}_INCLUDE_DIR "{{ include_dirs }}" )
            {% endif %}
            {% if libraries is not none %}
            set({{ prefix }}_LIBRARIES {{ libraries }} )
            {% endif %}
            {% if definitions is not none %}
            set({{ prefix }}_DEFINITIONS "{{ definitions}}" )
            {% endif %}
            {% endfor %}
    
            # build_modules_paths comes from last configuration only
            # Some build modules in RecipeCenter use try_compile variables and legacy, so this
            # include() needs to happen after the above variables are defined
            {% for build_module in build_modules_paths %}
            message(STATUS "Recipe: Including build module from '{{build_module}}'")
            include("{{ build_module }}")
            {% endfor %}
    
            # Definition of extra CMake variables from cmake_extra_variables
    
            {% for key, value in extra_variables.items() %}
            set({{ key }} {{ value }})
            {% endfor %}
            """)
