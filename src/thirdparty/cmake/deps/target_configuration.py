import os
import textwrap

import jinja2

from thirdparty._internal.model.info import PackageType
from thirdparty._internal.util.generators import relativize_path
from thirdparty.cmake.utils import cmake_escape_value
from thirdparty.errors import RecipeException

from typing import Any
from thirdparty.recipe import RecipeBase


# Source-language tokens (from Info.languages) that CMake recognizes as link-interface
# languages, mapped to CMake's own names. Info.languages is an OPEN list -- any ecosystem may
# appear -- but only tokens in this map become IMPORTED_LINK_INTERFACE_LANGUAGES. Others (Rust,
# Zig, Go, ...) link through CMake's default rules (like C), so they neither emit a bogus
# language nor trigger the "language not enabled in project()" error in the template below.
_CMAKE_LANGUAGES = {
    "C": "C",
    "C++": "CXX", "CXX": "CXX",
    "CUDA": "CUDA",
    "Objective-C": "OBJC", "OBJC": "OBJC",
    "Objective-C++": "OBJCXX", "OBJCXX": "OBJCXX",
    "Fortran": "Fortran",
    "Swift": "Swift",
    "ASM": "ASM",
    "HIP": "HIP",
    "ISPC": "ISPC",
    "RC": "RC",
}


class TargetConfigurationTemplate2:
    """
    FooTarget-release.cmake
    """

    def __init__(
        self,
        cmakedeps: Any,
        recipe: RecipeBase,
        require: Any,
        full_cpp_info: Any):
        self._cmakedeps = cmakedeps
        self._recipe = recipe  # The dependency recipe, not the consumer one
        self._require = require
        self._full_cpp_info = full_cpp_info

    def content(self) -> str:
        t = jinja2.Template(
            self._template, trim_blocks=True, lstrip_blocks=True, undefined=jinja2.StrictUndefined)
        return t.render(self._context)

    @property
    def filename(self) -> str:
        f = self._cmakedeps.get_cmake_filename(self._recipe)
        # Fallback to consumer configuration if it doesn't have build_type
        config = self._recipe.settings.build_type or self._cmakedeps.configuration
        config = (config or "none").lower()
        build = "Build" if self._recipe.is_build_context else ""
        return f"{f}-Targets{build}-{config}.cmake"

    def _requires(self, info: Any, components: Any) -> dict[str, Any]:
        result: dict[str, Any] = {}
        requires = info.parsed_requires()
        pkg_name = self._recipe.name
        pkg_type = info.type
        assert isinstance(pkg_type, PackageType), f"Pkg type {pkg_type} {type(pkg_type)}"
        transitive_reqs = self._cmakedeps.get_transitive_requires(self._recipe)

        if not requires and not components:  # global info without components definition
            # require the pkgname::pkgname base (user defined) or INTERFACE base target
            for req, d in transitive_reqs.items():
                if d.info.exe:
                    continue
                dep_target = self._cmakedeps.get_property("cmake_target_name", d)
                dep_target = dep_target or f"{d.name}::{d.name}"
                link_feature = self._cmakedeps.get_property("cmake_link_feature", d)
                link = req.libs
                result[dep_target] = {
                    "link": link, "link_feature": link_feature,
                }
            return result

        for required_pkg, required_comp in requires:
            if required_pkg is None:  # Points to a component of same package
                dep_comp = components.get(required_comp)
                assert dep_comp, f"Component {required_comp} not found in {self._recipe}"
                dep_target = self._cmakedeps.get_property(
                    "cmake_target_name", self._recipe, required_comp)
                dep_target = dep_target or f"{pkg_name}::{required_comp}"
                link_feature = self._cmakedeps.get_property(
                    "cmake_link_feature", self._recipe, required_comp)
                result[dep_target] = {
                    "link": True,  # Components of same package have PUBLIC dependency
                    "link_feature": link_feature,
                }
            else:  # Different package
                try:
                    req, dep = transitive_reqs.of(required_pkg)
                except KeyError:  # The transitive dep might have been skipped
                    pass
                else:
                    # To check if the component exist, it is ok to use the standard info
                    # No need to use the info = deduce_cpp_info(dep)
                    dep_comp = dep.info.components.get(required_comp)
                    if dep_comp is None:
                        # It must be the interface pkgname::pkgname target
                        if required_pkg != required_comp:
                            msg = (f"{self._recipe} recipe info did .requires to "
                                   f"'{required_pkg}::{required_comp}' but component "
                                   f"'{required_comp}' not found in {required_pkg}")
                            raise RecipeException(msg)
                        if dep.info.exe:
                            continue  # It doesn't make sense to link a package that is an App
                        comp = None
                        default_target = f"{dep.name}::{dep.name}"  # replace_requires
                        link = req.libs  # Do what the requirement to that package says
                    else:
                        if dep_comp.type is PackageType.APP or dep_comp.exe:
                            continue  # It doesn't make sense to link a package that is an App
                        comp = required_comp
                        default_target = f"{required_pkg}::{required_comp}"
                        # if it contains a requirement of a specific component of the other package
                        # and the other package can be an APP, but containing a LIB component
                        # the req.libs will not be defined. This is the libtool->automake(app) case
                        link = not (pkg_type is PackageType.SHARED and dep_comp.type is PackageType.SHARED)
                    link = req.libs or link
                    dep_target = self._cmakedeps.get_property("cmake_target_name", dep, comp)
                    dep_target = dep_target or default_target
                    link_feature = self._cmakedeps.get_property("cmake_link_feature", dep, comp)

                    result[dep_target] = {
                        "link": link, "link_feature": link_feature,
                    }
        return result

    @property
    def _context(self) -> dict[str, Any]:
        info = self._full_cpp_info
        assert isinstance(info.type, PackageType)
        pkg_name = self._recipe.name
        # fallback to consumer configuration if it doesn't have build_type
        config = self._recipe.settings.build_type or self._cmakedeps.configuration
        config = config.upper() if config else None
        pkg_folder = self._recipe.folders.package.as_posix()
        config_folder = f"_{config}" if config else ""
        build = "_BUILD" if self._recipe.is_build_context else ""
        pkg_folder_var = f"{pkg_name}_PACKAGE_FOLDER{config_folder}{build}"

        libs = {}
        # The BUILD context does not generate libraries targets atm
        if not self._require.build:
            libs = self._get_libs(info, pkg_name, pkg_folder, pkg_folder_var)
            self._add_root_lib_target(libs, pkg_name, info)
        exes = self._get_exes(info, pkg_name, pkg_folder, pkg_folder_var)

        seen_aliases: set[Any] = set()
        root_target_name = self._cmakedeps.get_property("cmake_target_name", self._recipe)
        root_target_name = root_target_name or f"{pkg_name}::{pkg_name}"
        for lib in libs.values():
            for alias in lib.get("cmake_target_aliases", []):
                if alias == root_target_name:
                    raise RecipeException(
                        f"Can't define an alias '{alias}' for the "
                        f"root target '{root_target_name}' in {self._recipe}. "
                        f"Changing the default target should be done with the "
                        f"'cmake_target_name' property.")
                if alias in seen_aliases:
                    raise RecipeException(f"Alias '{alias}' already defined in {self._recipe}. ")
                seen_aliases.add(alias)
                if alias in libs:
                    raise RecipeException(
                        f"Alias '{alias}' already defined as a target in "
                        f"{self._recipe}. ")

        pkg_folder = relativize_path(
            pkg_folder, self._cmakedeps._recipe, "${CMAKE_CURRENT_LIST_DIR}")
        dependencies = self._get_dependencies()
        return {
            "dependencies": dependencies, "pkg_folder": pkg_folder, "pkg_folder_var": pkg_folder_var, "config": config, "exes": exes, "libs": libs, "context": self._recipe.context,
        }

    def _get_libs(
        self,
        info: Any,
        pkg_name: str,
        pkg_folder: str,
        pkg_folder_var: str) -> dict[str, Any]:
        libs: dict[str, Any] = {}
        if info.has_components:
            for name, component in info.components.items():
                target_name = self._cmakedeps.get_property(
                    "cmake_target_name", self._recipe, name)
                target_name = target_name or f"{pkg_name}::{name}"
                target = self._get_cmake_lib(
                    component, info.components, pkg_folder, pkg_folder_var, comp_name=name)
                if target is not None:
                    cmake_target_aliases = self._get_aliases(name)
                    target["cmake_target_aliases"] = cmake_target_aliases
                    libs[target_name] = target
        else:
            target_name = self._cmakedeps.get_property("cmake_target_name", self._recipe)
            target_name = target_name or f"{pkg_name}::{pkg_name}"
            target = self._get_cmake_lib(info, None, pkg_folder, pkg_folder_var)
            if target is not None:
                cmake_target_aliases = self._get_aliases()
                target["cmake_target_aliases"] = cmake_target_aliases
                libs[target_name] = target
        return libs

    def _get_cmake_lib(
        self,
        info: Any,
        components: Any,
        pkg_folder: str,
        pkg_folder_var: str,
        comp_name: str | None = None) -> dict[str, Any] | None:
        if info.exe or not (info.package_framework or info.frameworks or info.includedirs or info.libs or info.system_libs or info.defines or info.requires):
            return

        includedirs = ";".join(
            self._path(i, pkg_folder, pkg_folder_var) for i in info.includedirs) if info.includedirs else ""
        requires = self._requires(info, components)
        assert isinstance(requires, dict)
        defines = ";".join(cmake_escape_value(f) for f in info.defines)
        # FIXME: Filter by lib traits!!!!!
        if not self._require.headers:  # If not depending on headers, paths and
            includedirs = defines = None
        extra_libs: list[Any] = self._cmakedeps.get_property(
            "cmake_extra_interface_libs", self._recipe, comp_name=comp_name, check_type=list) or []
        sources = [self._path(source, pkg_folder, pkg_folder_var) for source in info.sources]
        target: dict[str, Any] = {
            "type": "INTERFACE",
            "comp_name": comp_name,
            "includedirs": includedirs,
            "defines": defines,
            "requires": requires,
            "cxxflags": ";".join(cmake_escape_value(f) for f in info.cxxflags),
            "cflags": ";".join(cmake_escape_value(f) for f in info.cflags),
            "sharedlinkflags": ";".join(cmake_escape_value(v) for v in info.sharedlinkflags),
            "exelinkflags": ";".join(cmake_escape_value(v) for v in info.exelinkflags),
            "system_libs": " ".join(info.system_libs + extra_libs),
            "sources": " ".join(sources),
        }
        # System frameworks (only Apple OS)
        if info.frameworks:
            target["frameworks"] = " ".join([f"-framework {frw}" for frw in info.frameworks])
        # FIXME: We're ignoring this value at this moment. It relies on cmake_target_name or lib name
        #        Revisit when cpp.exe value is used too.
        if info.package_framework:
            target["package_framework"] = {}
            lib_type = "SHARED" if info.type is PackageType.SHARED else "STATIC" if info.type is PackageType.STATIC else "STATIC"
            assert lib_type, f"Unknown package type {info.type}"
            assert info.location, f"info.location missing for framework {info.package_framework}"
            target["type"] = lib_type
            target["package_framework"]["location"] = self._path(
                info.location, pkg_folder, pkg_folder_var)
            target["includedirs"] = []  # empty as frameworks have their own way to inject headers
            # FIXME: This is not needed for CMake < 3.24. Remove it when Recipe requires CMake >= 3.24
            target["package_framework"]["frameworkdir"] = self._path(
                pkg_folder, pkg_folder, pkg_folder_var)
        if info.libs:
            if len(info.libs) != 1:
                raise RecipeException(
                    f"New CMakeDeps only allows 1 lib per component:\n"
                    f"{self._recipe}: {info.libs}")
            assert info.location, "info.location missing for .libs, it should have been deduced"
            location = self._path(info.location, pkg_folder, pkg_folder_var)
            link_location = self._path(info.link_location, pkg_folder, pkg_folder_var) if info.link_location else None
            lib_type = "SHARED" if info.type is PackageType.SHARED else "STATIC" if info.type is PackageType.STATIC else None
            assert lib_type, f"Unknown package type {info.type}"
            target["type"] = lib_type
            target["location"] = location
            target["link_location"] = link_location
            # Keep only languages CMake knows (mapped to its names); Rust/Zig/... are dropped so
            # they link via CMake's default rules instead of erroring as an unknown link language.
            languages: list[str] = info.languages or []
            link_languages = [
                _CMAKE_LANGUAGES[c] for c in languages if c in _CMAKE_LANGUAGES]
            target["link_languages"] = link_languages
        return target

    def _get_aliases(self, comp_name: str | None = None) -> list[Any]:
        aliases: list[Any] = self._cmakedeps.get_property("cmake_target_aliases", self._recipe, comp_name, check_type=list) or []
        return aliases

    def _add_root_lib_target(
        self,
        libs: dict[str, Any],
        pkg_name: str,
        info: Any):
        """
        Add a new pkgname::pkgname INTERFACE target that depends on default_components or
        on all other library targets (not exes)
        It will not be added if there exists already a pkgname::pkgname target (Or an alias exists).
        """
        root_target_name = self._cmakedeps.get_property("cmake_target_name", self._recipe)
        root_target_name = root_target_name or f"{pkg_name}::{pkg_name}"
        # TODO: What if an exe target is called like the pkg_name::pkg_name
        if libs and root_target_name not in libs:
            # Add a generic interface target for the package depending on the others
            if info.default_components is not None:
                all_requires = {}
                for defaultc in info.default_components:
                    target_name = self._cmakedeps.get_property(
                        "cmake_target_name", self._recipe, defaultc)
                    comp_name = target_name or f"{pkg_name}::{defaultc}"
                    link_feature = self._cmakedeps.get_property(
                        "cmake_link_feature", self._recipe, defaultc)
                    all_requires[comp_name] = {
                        "link": True,  # It is an interface, full link
                        "link_feature": link_feature,
                    }
            else:
                all_requires = {k: {
                    "link": True, "link_feature": self._cmakedeps.get_property(
                        "cmake_link_feature", self._recipe, v.get("comp_name")),
                } for k, v in libs.items()}
            # This target might have an alias, so we need to check it
            cmake_target_aliases = self._get_aliases()
            libs[root_target_name] = {
                "type": "INTERFACE", "requires": all_requires, "cmake_target_aliases": cmake_target_aliases,
            }

    def _get_exes(
        self,
        info: Any,
        pkg_name: str,
        pkg_folder: str,
        pkg_folder_var: str) -> dict[str, Any]:
        exes: dict[str, Any] = {}

        if info.has_components:
            for name, comp in info.components.items():
                if comp.exe or comp.type is PackageType.APP:
                    target_name = self._cmakedeps.get_property(
                        "cmake_target_name", self._recipe, name)
                    target = target_name or f"{pkg_name}::{name}"
                    exe_location = self._path(comp.location, pkg_folder, pkg_folder_var)
                    exes[target] = exe_location
        else:
            if info.exe:
                target_name = self._cmakedeps.get_property("cmake_target_name", self._recipe)
                target = target_name or f"{pkg_name}::{pkg_name}"
                exe_location = self._path(info.location, pkg_folder, pkg_folder_var)
                exes[target] = exe_location

        return exes

    def _get_dependencies(self) -> dict[str, Any]:
        """ transitive dependencies Filenames for find_dependency()
        """
        # Build requires are already filtered by the get_transitive_requires
        transitive_reqs = self._cmakedeps.get_transitive_requires(self._recipe)
        # FIXME: Hardcoded CONFIG
        ret: dict[str, str] = {self._cmakedeps.get_cmake_filename(r): "CONFIG" for r in transitive_reqs.values()}
        extra_mods: list[Any] = self._cmakedeps.get_property(
            "cmake_extra_dependencies", self._recipe, check_type=list) or []
        ret.update({extra_mod: "" for extra_mod in extra_mods})
        return ret

    @staticmethod
    def _path(p: str, pkg_folder: str, pkg_folder_var: str) -> str:
        def escape(p_: str) -> str:
            return p_.replace("$", "\\$").replace('"', '\\"')

        p = p.replace("\\", "/")
        if os.path.isabs(p):
            if p.startswith(pkg_folder):
                rel = p[len(pkg_folder):].lstrip("/")
                return f"${{{pkg_folder_var}}}/{escape(rel)}"
            return escape(p)
        return f"${{{pkg_folder_var}}}/{escape(p)}"

    @property
    def _template(self) -> str:
        # TODO: CMake 3.24: Apple Frameworks: https://cmake.org/cmake/help/latest/manual/cmake-generator-expressions.7.html#genex:LINK_LIBRARY
        # TODO: Check why not set_property instead of target_link_libraries
        return textwrap.dedent(
            """
            {%- macro config_wrapper(config, value) -%}
                    {% if config -%}
                    $<$<CONFIG:{{config}}>:{{value}}>
                    {%- else -%}
                    {{value}}
                    {%- endif %}
            {%- endmacro -%}
            set({{pkg_folder_var}} "{{pkg_folder}}")
    
            # Dependencies finding
            include(CMakeFindDependencyMacro)
    
            {% for dep, dep_find_mode in dependencies.items() %}
            if(NOT {{dep}}_FOUND)
                find_dependency({{dep}} REQUIRED {{dep_find_mode}})
            endif()
            {% endfor %}
    
            ################# Libs information ##############
            {% for lib, lib_info in libs.items() %}
            #################### {{lib}} ####################
            if(NOT TARGET {{ lib }})
                message(STATUS "Recipe: Target declared imported {{lib_info["type"]}} library '{{lib}}'")
                add_library({{lib}} {{lib_info["type"]}} IMPORTED)
            endif()
            {% for alias in lib_info.get("cmake_target_aliases", []) %}
            if(NOT TARGET {{alias}})
                message(STATUS "Recipe: Target declared alias '{{alias}}' for '{{lib}}'")
                add_library({{alias}} ALIAS {{lib}})
            endif()
            {% endfor %}
            {% if lib_info.get("includedirs") %}
            set_property(TARGET {{lib}} APPEND PROPERTY INTERFACE_INCLUDE_DIRECTORIES
                            {{config_wrapper(config, lib_info["includedirs"])}})
            {% endif %}
            {% if lib_info.get("defines") %}
            set_property(TARGET {{lib}} APPEND PROPERTY INTERFACE_COMPILE_DEFINITIONS
                            "{{config_wrapper(config, lib_info["defines"])}}")
            {% endif %}
            {% if lib_info.get("cxxflags") %}
            set_property(TARGET {{lib}} APPEND PROPERTY INTERFACE_COMPILE_OPTIONS
                            "$<$<COMPILE_LANGUAGE:CXX>:{{config_wrapper(config, lib_info["cxxflags"])}}>")
            {% endif %}
            {% if lib_info.get("cflags") %}
            set_property(TARGET {{lib}} APPEND PROPERTY INTERFACE_COMPILE_OPTIONS
                            "$<$<COMPILE_LANGUAGE:C>:{{config_wrapper(config, lib_info["cflags"])}}>")
            {% endif %}
            {% if lib_info.get("sharedlinkflags") %}
            {% set linkflags = config_wrapper(config, lib_info["sharedlinkflags"]) %}
            set_property(TARGET {{lib}} APPEND PROPERTY INTERFACE_LINK_OPTIONS
                            "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,SHARED_LIBRARY>:{{linkflags}}>"
                            "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,MODULE_LIBRARY>:{{linkflags}}>")
            {% endif %}
            {% if lib_info.get("exelinkflags") %}
            {% set exeflags = config_wrapper(config, lib_info["exelinkflags"]) %}
            set_property(TARGET {{lib}} APPEND PROPERTY INTERFACE_LINK_OPTIONS
                            "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,EXECUTABLE>:{{exeflags}}>")
            {% endif %}
    
            {% if lib_info.get("link_languages") %}
            get_property(_languages GLOBAL PROPERTY ENABLED_LANGUAGES)
            if("CXX" IN_LIST _languages)
                list(APPEND _languages "C")
            endif()
            if("CUDA" IN_LIST _languages)
                list(APPEND _languages "C" "CXX")
            endif()
            {% for lang in lib_info["link_languages"] %}
            if(NOT "{{lang}}" IN_LIST _languages)
                message(SEND_ERROR
                        "Target {{lib}} has {{lang}} linkage but {{lang}} not enabled in project()")
            endif()
            set_property(TARGET {{lib}} APPEND PROPERTY
                            IMPORTED_LINK_INTERFACE_LANGUAGES_{{config}} {{lang}})
            {% endfor %}
            {% endif %}
            {% if lib_info.get("location") %}
            set_property(TARGET {{lib}} APPEND PROPERTY IMPORTED_CONFIGURATIONS {{config}})
            set_target_properties({{lib}} PROPERTIES IMPORTED_LOCATION_{{config}}
                                    "{{lib_info["location"]}}")
            {% elif lib_info.get("type") == "INTERFACE" %}
            set_property(TARGET {{lib}} APPEND PROPERTY IMPORTED_CONFIGURATIONS {{config}})
            {% endif %}
            {% if lib_info.get("link_location") %}
            set_target_properties({{lib}} PROPERTIES IMPORTED_IMPLIB_{{config}}
                                    "{{lib_info["link_location"]}}")
            {% endif %}
    
            {% if lib_info.get("requires") %}
            # Information of transitive dependencies
            {% for require_target, link_info in lib_info["requires"].items() %}
    
            # Requirement {{lib}} -> {{require_target}} (Full link: {{link_info["link"]}})
            {% if link_info["link"] %}
            {% if link_info["link_feature"] %}
            # Link feature: {{link_info["link_feature"]}}
            if(CMAKE_VERSION VERSION_LESS "3.24")
                message(FATAL_ERROR "The 'CMakeDeps' generator LINK_FEATURE property only works with CMake >= 3.24")
            endif()
            {% endif %}
            # set property allows to append, and lib_info[requires] will iterate
            set_property(TARGET {{lib}} APPEND PROPERTY INTERFACE_LINK_LIBRARIES
                {% if link_info["link_feature"] %}
                            "$<LINK_LIBRARY:{{link_info["link_feature"]}},{{config_wrapper(config, require_target)}}>")
                {% else %}
                            "{{config_wrapper(config, require_target)}}")
                {% endif %}
            {% else %}
            if(CMAKE_VERSION VERSION_LESS "3.27")
                message(FATAL_ERROR "The 'CMakeDeps' generator COMPILE_ONLY expression only works with CMake >= 3.27")
            endif()
            # If the headers trait is not there, this will do nothing
            target_link_libraries({{lib}} INTERFACE
                                    $<COMPILE_ONLY:{{config_wrapper(config, require_target)}}> )
            set_property(TARGET {{lib}} APPEND PROPERTY IMPORTED_LINK_DEPENDENT_LIBRARIES_{{config}}
                            {{require_target}})
            {% endif %}
            {% endfor %}
            {% endif %}
    
            {% if lib_info.get("system_libs") %}
            set_property(TARGET {{lib}} APPEND PROPERTY INTERFACE_LINK_LIBRARIES
                            {{config_wrapper(config, lib_info["system_libs"])}})
            {% endif %}
            {% if lib_info.get("frameworks") %}
            set_property(TARGET {{lib}} APPEND PROPERTY INTERFACE_LINK_LIBRARIES
                            "{{config_wrapper(config, lib_info["frameworks"])}}")
            {% endif %}
            {% if lib_info.get("package_framework") %}
            set_target_properties({{lib}} PROPERTIES
                IMPORTED_LOCATION_{{config}} "{{lib_info["package_framework"]["location"]}}"
                FRAMEWORK TRUE)
            if(CMAKE_VERSION VERSION_LESS "3.24")
                set_property(TARGET {{lib}} APPEND PROPERTY INTERFACE_COMPILE_OPTIONS
                                $<$<COMPILE_LANGUAGE:CXX>:-F{{lib_info["package_framework"]["frameworkdir"]}}>)
                set_property(TARGET {{lib}} APPEND PROPERTY INTERFACE_COMPILE_OPTIONS
                                $<$<COMPILE_LANGUAGE:C>:-F{{lib_info["package_framework"]["frameworkdir"]}}>)
            endif()
            {% endif %}
    
            {% if lib_info.get("sources") %}
            set_property(TARGET {{lib}} APPEND PROPERTY INTERFACE_SOURCES
                            {{config_wrapper(config, lib_info["sources"] )}})
            {% endif %}
            {% endfor %}
    
            ################# Exes information ##############
            {% for exe, location in exes.items() %}
            #################### {{exe}} ####################
            if(NOT TARGET {{ exe }})
                message(STATUS "Recipe: Target declared imported executable '{{exe}}' {{context}}")
                add_executable({{exe}} IMPORTED)
            else()
                get_property(_context TARGET {{exe}} PROPERTY RECIPE_CONTEXT)
                if(NOT $${_context} STREQUAL "{{context}}")
                    message(STATUS "Recipe: Exe {{exe}} was already defined in ${_context}")
                    get_property(_configurations TARGET {{exe}} PROPERTY IMPORTED_CONFIGURATIONS)
                    message(STATUS "Recipe: Exe {{exe}} defined configurations: ${_configurations}")
                    foreach(_config ${_configurations})
                        set_property(TARGET {{exe}} PROPERTY IMPORTED_LOCATION_${_config})
                    endforeach()
                    set_property(TARGET {{exe}} PROPERTY IMPORTED_CONFIGURATIONS)
                endif()
            endif()
            set_property(TARGET {{exe}} APPEND PROPERTY IMPORTED_CONFIGURATIONS {{config}})
            set_target_properties({{exe}} PROPERTIES IMPORTED_LOCATION_{{config}} "{{location}}")
            set_property(TARGET {{exe}} PROPERTY RECIPE_CONTEXT "{{context}}")
            {% endfor %}
            """)
