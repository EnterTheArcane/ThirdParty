import jinja2
import os
import re
import textwrap

from thirdparty._internal.model.version import Version
from thirdparty._internal.subsystems import deduce_subsystem, WINDOWS
from thirdparty._internal.util.files import load
from thirdparty._internal.util.generators import relativize_path
from thirdparty.android import android_abi
from thirdparty.apple.utils import get_apple_sdk_fullname, _to_apple_arch
from thirdparty.apple.utils import is_apple_os, to_apple_arch
from thirdparty.build import build_jobs
from thirdparty.build.cross_building import cross_building
from thirdparty.build.flags import architecture_flag, architecture_link_flag, libcxx_flags, threads_flags
from thirdparty.cmake.toolchain import RECIPE_TOOLCHAIN_FILENAME
from thirdparty.cmake.utils import is_multi_configuration
from thirdparty.errors import RecipeException
from thirdparty.microsoft.visual import msvc_version_to_toolset_version, msvc_platform_from_arch

from typing import Any, cast
from thirdparty.recipe import RecipeBase


class Block:
    def __init__(
        self,
        recipe: RecipeBase,
        toolchain: Any,
        name: str):
        self._recipe = recipe
        self._toolchain = toolchain
        self._context_values: dict[str, Any] | None = None
        self._name = name

    @property
    def values(self) -> dict[str, Any] | None:
        if self._context_values is None:
            self._context_values = self.context()
        return self._context_values

    @values.setter
    def values(self, context_values: dict[str, Any] | None):
        self._context_values = context_values

    def get_rendered_content(self) -> str | None:
        context = self.values
        if context is None:
            return

        template = f"########## '{self._name}' block #############\n" + self.template + "\n\n"
        template = jinja2.Template(template, trim_blocks=True, lstrip_blocks=True)
        return template.render(**context)

    def context(self) -> dict[str, Any] | None:
        return {}

    template: str


class VSRuntimeBlock(Block):
    template = textwrap.dedent(
        """
        # Definition of VS runtime CMAKE_MSVC_RUNTIME_LIBRARY, from settings build_type,
        # compiler.runtime, compiler.runtime_type

        {% set genexpr = namespace(str='') %}
        {% for config, value in vs_runtimes.items() %}
            {% set genexpr.str = genexpr.str +
                                    '$<$<CONFIG:' + config + '>:' + value|string + '>' %}
        {% endfor %}
        cmake_policy(GET CMP0091 POLICY_CMP0091)
        if(NOT "${POLICY_CMP0091}" STREQUAL NEW)
            message(FATAL_ERROR "The CMake policy CMP0091 must be NEW, but is '${POLICY_CMP0091}'")
        endif()
        message(STATUS "Recipe toolchain: Setting CMAKE_MSVC_RUNTIME_LIBRARY={{ genexpr.str  }}")
        set(CMAKE_MSVC_RUNTIME_LIBRARY "{{ genexpr.str }}")
        """)

    def context(self) -> dict[str, Any] | None:
        # Parsing existing toolchain file to get existing configured runtimes
        settings = self._recipe.settings
        if settings.os != "Windows":
            return

        compiler = settings.compiler
        if compiler not in ("msvc", "clang"):
            return

        runtime = settings.compiler_runtime
        if runtime is None:
            return

        config_dict = {}
        if os.path.exists(RECIPE_TOOLCHAIN_FILENAME):
            existing_include = load(RECIPE_TOOLCHAIN_FILENAME)
            msvc_runtime_value = re.search(
                r"set\(CMAKE_MSVC_RUNTIME_LIBRARY \"([^)]*)\"\)", existing_include)
            if msvc_runtime_value:
                capture = msvc_runtime_value.group(1)
                matches = re.findall(r"\$<\$<CONFIG:([A-Za-z]*)>:([A-Za-z]*)>", capture)
                config_dict = dict(matches)

        build_type = settings.build_type  # FIXME: change for configuration
        if build_type is None:  # pyright: ignore[reportUnnecessaryComparison] -- defensive: build_type declared str but may be unset at runtime
            return None

        if compiler == "msvc" or compiler == "clang":
            runtime_type = settings.compiler_runtime_type
            rt = "MultiThreadedDebug" if runtime_type == "Debug" else "MultiThreaded"
            if runtime != "static":
                rt += "DLL"
            config_dict[build_type] = rt

            # If clang is being used the CMake check of compiler will try to create a simple
            # test application, and will fail because the Debug runtime is not there
            if compiler == "clang":
                if config_dict.get("Debug") is None:
                    clang_rt = "MultiThreadedDebug" + ("DLL" if runtime != "static" else "")
                    config_dict["Debug"] = clang_rt

        return {"vs_runtimes": config_dict}


class VSDebuggerEnvironment(Block):
    template = textwrap.dedent(
        """
        # Definition of CMAKE_VS_DEBUGGER_ENVIRONMENT from "bindirs" folders of dependencies
        # for execution of applications with shared libraries within the VS IDE

        {% if vs_debugger_path %}
        # if the file exists it will be loaded by FindFiles block and the variable defined there
        if(NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/recipe_cmakedeps_paths.cmake")
        # This variable requires CMake>=3.27 to work
        set(CMAKE_VS_DEBUGGER_ENVIRONMENT "{{ vs_debugger_path }}")
        endif()
        {% endif %}
        """)

    def context(self) -> dict[str, Any] | None:
        os_ = self._recipe.settings.os
        build_type = self._recipe.settings.build_type

        if (os_ and "Windows" not in os_) or not build_type:
            return None

        if "Visual" not in self._toolchain.generator:
            return None

        config_dict = {}
        if os.path.exists(RECIPE_TOOLCHAIN_FILENAME):
            existing_include = load(RECIPE_TOOLCHAIN_FILENAME)
            pattern = r"set\(CMAKE_VS_DEBUGGER_ENVIRONMENT \"PATH=([^)]*);%PATH%\"\)"
            vs_debugger_environment = re.search(pattern, existing_include)
            if vs_debugger_environment:
                capture = vs_debugger_environment.group(1)
                matches = re.findall(r"\$<\$<CONFIG:([A-Za-z]*)>:([^>]*)>", capture)
                config_dict = dict(matches)

        host_deps = self._recipe.dependencies.host.values()
        bin_dirs = [p for dep in host_deps for p in dep.info.aggregated_components().bindirs]
        bin_dirs = [relativize_path(p, self._recipe, "${CMAKE_CURRENT_LIST_DIR}") for p in bin_dirs]
        bin_dirs = [p.replace("\\", "/") for p in bin_dirs]
        bin_dirs = ";".join(bin_dirs) if bin_dirs else None
        if bin_dirs:
            config_dict[build_type] = bin_dirs

        if not config_dict:
            return None

        vs_debugger_path = ""
        for config, value in config_dict.items():
            vs_debugger_path += f"$<$<CONFIG:{config}>:{value}>"
        vs_debugger_path = f"PATH={vs_debugger_path};%PATH%"
        return {"vs_debugger_path": vs_debugger_path}


class FPicBlock(Block):
    template = textwrap.dedent(
        """
        # Defining CMAKE_POSITION_INDEPENDENT_CODE for static libraries when necessary

        {% if pic %}
        message(STATUS "Recipe toolchain: Setting CMAKE_POSITION_INDEPENDENT_CODE={{ pic }} (options.pic)")
        set(CMAKE_POSITION_INDEPENDENT_CODE {{ pic }} CACHE BOOL "Position independent code")
        {% endif %}
        """)

    def context(self) -> dict[str, Any] | None:
        pic = self._recipe.options.get_safe("pic")
        if pic is None:
            return None
        os_ = self._recipe.settings.os
        if os_ and "Windows" in os_:
            return None
        return {"pic": "ON" if pic else "OFF"}


class GLibCXXBlock(Block):
    template = textwrap.dedent(
        """
        # Definition of libcxx from 'compiler.libcxx' setting, defining the
        # right CXX_FLAGS for that libcxx

        {% if set_libcxx %}
        message(STATUS "Recipe toolchain: Defining libcxx as C++ flags: {{ set_libcxx }}")
        string(APPEND RECIPE_CXX_FLAGS " {{ set_libcxx }}")
        {% endif %}
        {% if glibcxx %}
        message(STATUS "Recipe toolchain: Adding glibcxx compile definition: {{ glibcxx }}")
        add_compile_definitions({{ glibcxx }})
        {% endif %}
        """)

    def context(self) -> dict[str, Any] | None:
        libcxx, stdlib11 = libcxx_flags(self._recipe)
        return {"set_libcxx": libcxx, "glibcxx": stdlib11}


class SkipRPath(Block):
    template = textwrap.dedent(
        """
        # Defining CMAKE_SKIP_RPATH

        {% if skip_rpath %}
        set(CMAKE_SKIP_RPATH 1 CACHE BOOL "rpaths" FORCE)
        # Policy CMP0068
        # We want the old behavior, in CMake >= 3.9 CMAKE_SKIP_RPATH won't affect install_name in OSX
        set(CMAKE_INSTALL_NAME_DIR "")
        {% endif %}
        """)

    skip_rpath = False

    def context(self) -> dict[str, Any] | None:
        return {"skip_rpath": self.skip_rpath}


class ArchitectureBlock(Block):
    template = textwrap.dedent(
        """
        {% if arch_flag %}
        # Define C++ flags, C flags and linker flags from 'settings.arch'
        message(STATUS "Recipe toolchain: Defining architecture flag: {{ arch_flag }}")
        string(APPEND RECIPE_CXX_FLAGS " {{ arch_flag }}")
        string(APPEND RECIPE_C_FLAGS " {{ arch_flag }}")
        string(APPEND RECIPE_SHARED_LINKER_FLAGS " {{ arch_flag }}")
        string(APPEND RECIPE_EXE_LINKER_FLAGS " {{ arch_flag }}")
        {% endif %}
        {% if arch_link_flag %}
        message(STATUS "Recipe toolchain: Defining architecture linker flag: {{ arch_link_flag }}")
        string(APPEND RECIPE_SHARED_LINKER_FLAGS " {{ arch_link_flag }}")
        string(APPEND RECIPE_EXE_LINKER_FLAGS " {{ arch_link_flag }}")
        {% endif %}
        {% if thread_flags_list %}
        # Define C++ flags, C flags and linker flags from 'compiler.threads'
        message(STATUS "Recipe toolchain: Defining thread flags: {{ thread_flags_list }}")
        string(APPEND RECIPE_CXX_FLAGS " {{ thread_flags_list }}")
        string(APPEND RECIPE_C_FLAGS " {{ thread_flags_list }}")
        string(APPEND RECIPE_SHARED_LINKER_FLAGS " {{ thread_flags_list }}")
        string(APPEND RECIPE_EXE_LINKER_FLAGS " {{ thread_flags_list }}")
        {% endif %}
        """)

    def context(self) -> dict[str, Any] | None:
        arch_flag = architecture_flag(self._recipe)
        arch_link_flag = architecture_link_flag(self._recipe)
        thread_flags_list = " ".join(threads_flags(self._recipe))
        if not arch_flag and not arch_link_flag and not thread_flags_list:
            return
        return {
            "arch_flag": arch_flag, "arch_link_flag": arch_link_flag, "thread_flags_list": thread_flags_list,
        }


class RpathLinkFlagsBlock(Block):
    template = textwrap.dedent(
        """
        # Pass -rpath-link pointing to all directories with runtime libraries
        {% if rpath_link_flags %}
        string(APPEND RECIPE_EXE_LINKER_FLAGS " {{ rpath_link_flags }}")
        string(APPEND RECIPE_SHARED_LINKER_FLAGS " {{ rpath_link_flags }}")
        {% endif %}
        """)

    def context(self) -> dict[str, Any] | None:
        add_rpath_link = self._toolchain.add_rpath_link or self._recipe.conf.tools.build.add_rpath_link
        if add_rpath_link:
            runtime_dirs: list[Any] = []
            host_req = self._recipe.dependencies.filter({"build": False}).values()
            for req in host_req:
                cppinfo = req.info.aggregated_components()
                runtime_dirs.extend(cppinfo.libdirs)

            # surround each dir with escaped quotes, to avoid problems with spaces in paths
            rpath_link_flags = " ".join([f'-Wl,-rpath-link=\\"{d}\\"' for d in runtime_dirs]) if runtime_dirs else None
        else:
            rpath_link_flags = None
        return {"rpath_link_flags": rpath_link_flags}


class LinkerScriptsBlock(Block):
    template = textwrap.dedent(
        """
        # Add linker flags from tools.build:linker_scripts conf

        message(STATUS "Recipe toolchain: Defining linker script flag: {{ linker_script_flags }}")
        string(APPEND RECIPE_EXE_LINKER_FLAGS " {{ linker_script_flags }}")
        """)

    def context(self) -> dict[str, Any] | None:
        linker_scripts = self._recipe.conf.tools.build.linker_scripts
        if not linker_scripts:
            return
        linker_scripts = [linker_script.replace("\\", "/") for linker_script in linker_scripts]
        linker_scripts = [relativize_path(p, self._recipe, "${CMAKE_CURRENT_LIST_DIR}") for p in linker_scripts]
        linker_script_flags = [r'-T\"' + linker_script + r'\"' for linker_script in linker_scripts]
        return {"linker_script_flags": " ".join(linker_script_flags)}


class CppStdBlock(Block):
    template = textwrap.dedent(
        """
        # Define the C++ and C standards from 'compiler.cppstd' and 'compiler.cstd'

        function(recipe_modify_std_watch variable access value current_list_file stack)
            set(recipe_watched_std_variable "{{ cppstd }}")
            if (${variable} STREQUAL "CMAKE_C_STANDARD")
                set(recipe_watched_std_variable "{{ cstd }}")
            endif()
            if ("${access}" STREQUAL "MODIFIED_ACCESS" AND NOT "${value}" STREQUAL "${recipe_watched_std_variable}")
                message(STATUS "Warning: Standard ${variable} value defined in recipe_toolchain.cmake to ${recipe_watched_std_variable} has been modified to ${value} by ${current_list_file}")
            endif()
            unset(recipe_watched_std_variable)
        endfunction()

        {% if cppstd %}
        message(STATUS "Recipe toolchain: C++ Standard {{ cppstd }} with extensions {{ cppstd_extensions }}")
        set(CMAKE_CXX_STANDARD {{ cppstd }})
        set(CMAKE_CXX_EXTENSIONS {{ cppstd_extensions }})
        set(CMAKE_CXX_STANDARD_REQUIRED ON)
        variable_watch(CMAKE_CXX_STANDARD recipe_modify_std_watch)
        {% endif %}
        {% if cstd %}
        message(STATUS "Recipe toolchain: C Standard {{ cstd }} with extensions {{ cstd_extensions }}")
        set(CMAKE_C_STANDARD {{ cstd }})
        set(CMAKE_C_EXTENSIONS {{ cstd_extensions }})
        set(CMAKE_C_STANDARD_REQUIRED ON)
        variable_watch(CMAKE_C_STANDARD recipe_modify_std_watch)
        {% endif %}
        """)

    def context(self) -> dict[str, Any] | None:
        compiler_cppstd = self._recipe.settings.compiler_cxx_standard
        compiler_cstd = self._recipe.settings.compiler_c_standard
        result: dict[str, Any] = {}
        if compiler_cppstd is not None:
            if compiler_cppstd.startswith("gnu"):
                result["cppstd"] = compiler_cppstd[3:]
                result["cppstd_extensions"] = "ON"
            else:
                result["cppstd"] = compiler_cppstd
                result["cppstd_extensions"] = "OFF"
        if compiler_cstd is not None:
            if compiler_cstd.startswith("gnu"):
                result["cstd"] = compiler_cstd[3:]
                result["cstd_extensions"] = "ON"
            else:
                result["cstd"] = compiler_cstd
                result["cstd_extensions"] = "OFF"
        return result or None


class SharedLibBock(Block):
    template = textwrap.dedent(
        """
        # Define BUILD_SHARED_LIBS for shared libraries

        message(STATUS "Recipe toolchain: Setting BUILD_SHARED_LIBS = {{ shared_libs }}")
        set(BUILD_SHARED_LIBS {{ shared_libs }} CACHE BOOL "Build shared libraries")
        """)

    def context(self) -> dict[str, Any] | None:
        try:
            shared_libs = "ON" if self._recipe.options.shared else "OFF"
            return {"shared_libs": shared_libs}
        except RecipeException:
            return None


class ParallelBlock(Block):
    template = textwrap.dedent(
        """
        # Define VS paralell build /MP flags

        string(APPEND RECIPE_CXX_FLAGS " /MP{{ parallel }}")
        string(APPEND RECIPE_C_FLAGS " /MP{{ parallel }}")
        """)

    def context(self) -> dict[str, Any] | None:
        # TODO: Check this conf
        compiler = self._recipe.settings.compiler
        if compiler != "msvc" or "Visual" not in self._toolchain.generator:
            return

        jobs = build_jobs(self._recipe)
        if jobs:
            return {"parallel": jobs}


class AndroidSystemBlock(Block):
    template = textwrap.dedent(
        """
        # Define Android variables ANDROID_PLATFORM, ANDROID_STL, ANDROID_ABI, etc
        # and include(.../android.toolchain.cmake) from NDK toolchain file

        # New Android toolchain definitions
        message(STATUS "Recipe toolchain: Setting Android platform: {{ android_platform }}")
        set(ANDROID_PLATFORM {{ android_platform }})
        {% if android_stl %}
        message(STATUS "Recipe toolchain: Setting Android stl: {{ android_stl }}")
        set(ANDROID_STL {{ android_stl }})
        {% endif %}
        message(STATUS "Recipe toolchain: Setting Android abi: {{ android_abi }}")
        set(ANDROID_ABI {{ android_abi }})
        {% if android_use_legacy_toolchain_file %}
        set(ANDROID_USE_LEGACY_TOOLCHAIN_FILE {{ android_use_legacy_toolchain_file }})
        {% endif %}
        include("{{ android_ndk_path }}/build/cmake/android.toolchain.cmake")
        """)

    def context(self) -> dict[str, Any] | None:
        os_ = self._recipe.settings.os
        if os_ != "Android":
            return

        # TODO: only 'c++_shared' y 'c++_static' supported?
        #  https://developer.android.com/ndk/guides/cpp-support
        libcxx_str = self._recipe.settings.compiler_libcxx

        android_ndk_path = self._recipe.conf.tools.android.ndk_path
        if not android_ndk_path:
            raise RecipeException("CMakeToolchain needs conf.tools.android.ndk_path configuration defined")
        android_ndk_path = os.fspath(android_ndk_path).replace("\\", "/")
        android_ndk_path = relativize_path(
            android_ndk_path, self._recipe, "${CMAKE_CURRENT_LIST_DIR}")

        use_cmake_legacy_toolchain = self._recipe.conf.tools.android.cmake_legacy_toolchain
        if use_cmake_legacy_toolchain is not None:
            use_cmake_legacy_toolchain = "ON" if use_cmake_legacy_toolchain else "OFF"

        ctxt_toolchain = {
            "android_platform": "android-" + str(self._recipe.settings.os_api_level),
            "android_abi": android_abi(self._recipe),
            "android_stl": libcxx_str,
            "android_ndk_path": android_ndk_path,
            "android_use_legacy_toolchain_file": use_cmake_legacy_toolchain,
        }
        return ctxt_toolchain


class AppleSystemBlock(Block):
    template = textwrap.dedent(
        """
        # Define Apple architectures, sysroot, deployment target, bitcode, etc

        # Set the architectures for which to build.
        set(CMAKE_OSX_ARCHITECTURES {{ cmake_osx_architectures }} CACHE STRING "" FORCE)
        # Setting CMAKE_OSX_SYSROOT SDK, when using Xcode generator the name is enough
        # but full path is necessary for others
        set(CMAKE_OSX_SYSROOT {{ cmake_osx_sysroot }} CACHE STRING "" FORCE)
        {% if cmake_osx_deployment_target is defined %}
        # Setting CMAKE_OSX_DEPLOYMENT_TARGET if "os.version" is defined by the used recipe profile
        set(CMAKE_OSX_DEPLOYMENT_TARGET "{{ cmake_osx_deployment_target }}" CACHE STRING "")
        {% endif %}
        set(BITCODE "")
        set(FOBJC_ARC "")
        set(VISIBILITY "")
        {% if enable_bitcode %}
        # Bitcode ON
        set(CMAKE_XCODE_ATTRIBUTE_ENABLE_BITCODE "YES")
        set(CMAKE_XCODE_ATTRIBUTE_BITCODE_GENERATION_MODE "bitcode")
        {% if enable_bitcode_marker %}
        set(BITCODE "-fembed-bitcode-marker")
        {% else %}
        set(BITCODE "-fembed-bitcode")
        {% endif %}
        {% elif enable_bitcode is not none %}
        # Bitcode OFF
        set(CMAKE_XCODE_ATTRIBUTE_ENABLE_BITCODE "NO")
        {% endif %}
        {% if enable_arc %}
        # ARC ON
        set(FOBJC_ARC "-fobjc-arc")
        set(CMAKE_XCODE_ATTRIBUTE_CLANG_ENABLE_OBJC_ARC "YES")
        {% elif enable_arc is not none %}
        # ARC OFF
        set(FOBJC_ARC "-fno-objc-arc")
        set(CMAKE_XCODE_ATTRIBUTE_CLANG_ENABLE_OBJC_ARC "NO")
        {% endif %}
        {% if enable_visibility %}
        # Visibility ON
        set(CMAKE_XCODE_ATTRIBUTE_GCC_SYMBOLS_PRIVATE_EXTERN "NO")
        set(VISIBILITY "-fvisibility=default")
        {% elif enable_visibility is not none %}
        # Visibility OFF
        set(VISIBILITY "-fvisibility=hidden -fvisibility-inlines-hidden")
        set(CMAKE_XCODE_ATTRIBUTE_GCC_SYMBOLS_PRIVATE_EXTERN "YES")
        {% endif %}
        #Check if Xcode generator is used, since that will handle these flags automagically
        if(CMAKE_GENERATOR MATCHES "Xcode")
            message(DEBUG "Not setting any manual command-line buildflags, since Xcode is selected as generator.")
        else()
            string(APPEND RECIPE_C_FLAGS " ${BITCODE} ${VISIBILITY}")
            string(APPEND RECIPE_CXX_FLAGS " ${BITCODE} ${VISIBILITY}")
            # Objective-C/C++ specific flags
            string(APPEND RECIPE_OBJC_FLAGS " ${BITCODE} ${VISIBILITY} ${FOBJC_ARC}")
            string(APPEND RECIPE_OBJCXX_FLAGS " ${BITCODE} ${VISIBILITY} ${FOBJC_ARC}")
        endif()
        """)

    def context(self) -> dict[str, Any] | None:
        if not is_apple_os(self._recipe):
            return None

        def to_apple_archs(recipe: RecipeBase):
            """converts recipe-style architecture into Apple-style arch"""
            arch_ = recipe.settings.arch if recipe else None
            if arch_ is not None:
                return _to_apple_arch(arch_, default=arch_)

        host_architecture = to_apple_archs(self._recipe)

        host_os_version = self._recipe.settings.os_version
        host_sdk_name = self._recipe.conf.tools.apple.sdk_path or get_apple_sdk_fullname(self._recipe)
        is_debug = self._recipe.settings.build_type == "Debug"

        # Reading some configurations to enable or disable some Xcode toolchain flags and variables
        # Issue related: upstream issue 9448
        # Based on https://github.com/leetal/ios-cmake repository
        enable_bitcode = self._recipe.conf.tools.apple.enable_bitcode
        enable_arc = self._recipe.conf.tools.apple.enable_arc
        enable_visibility = self._recipe.conf.tools.apple.enable_visibility

        ctxt_toolchain: dict[str, Any] = {
            "enable_bitcode": enable_bitcode, "enable_bitcode_marker": all([enable_bitcode, is_debug]), "enable_arc": enable_arc, "enable_visibility": enable_visibility,
        }
        if host_sdk_name:
            host_sdk_name = relativize_path(
                os.fspath(host_sdk_name), self._recipe, "${CMAKE_CURRENT_LIST_DIR}")
            ctxt_toolchain["cmake_osx_sysroot"] = host_sdk_name
        # this is used to initialize the OSX_ARCHITECTURES property on each target as it is created
        if host_architecture:
            ctxt_toolchain["cmake_osx_architectures"] = host_architecture

        if host_os_version:
            # https://cmake.org/cmake/help/latest/variable/CMAKE_OSX_DEPLOYMENT_TARGET.html
            # Despite the OSX part in the variable name(s) they apply also to other SDKs than
            # macOS like iOS, tvOS, watchOS or visionOS.
            ctxt_toolchain["cmake_osx_deployment_target"] = host_os_version

        return ctxt_toolchain


class FindFiles(Block):
    template = textwrap.dedent(
        """
        # Define paths to find packages, programs, libraries, etc.
        if(EXISTS "${CMAKE_CURRENT_LIST_DIR}/recipe_cmakedeps_paths.cmake")
            message(STATUS "Recipe toolchain: Including CMakeDeps generated recipe_cmakedeps_paths.cmake")
            include("${CMAKE_CURRENT_LIST_DIR}/recipe_cmakedeps_paths.cmake")
        else()

        {% if find_package_prefer_config %}
        set(CMAKE_FIND_PACKAGE_PREFER_CONFIG {{ find_package_prefer_config }})
        {% endif %}

        # Definition of CMAKE_MODULE_PATH
        {% if build_paths %}
        list(PREPEND CMAKE_MODULE_PATH {{ build_paths }})
        {% endif %}
        {% if generators_folder %}
        # the generators folder (where recipe generates files, like this toolchain)
        list(PREPEND CMAKE_MODULE_PATH {{ generators_folder }})
        {% endif %}

        # Definition of CMAKE_PREFIX_PATH, CMAKE_XXXXX_PATH
        {% if build_paths %}
        # The explicitly defined "builddirs" of "host" context dependencies must be in PREFIX_PATH
        list(PREPEND CMAKE_PREFIX_PATH {{ build_paths }})
        {% endif %}
        {% if generators_folder %}
        # The Recipe local "generators" folder, where this toolchain is saved.
        list(PREPEND CMAKE_PREFIX_PATH {{ generators_folder }} )
        {% endif %}
        {% if cmake_program_path %}
        list(PREPEND CMAKE_PROGRAM_PATH {{ cmake_program_path }})
        {% endif %}
        {% if cmake_library_path %}
        list(PREPEND CMAKE_LIBRARY_PATH {{ cmake_library_path }})
        {% endif %}
        {% if is_apple and cmake_framework_path %}
        list(PREPEND CMAKE_FRAMEWORK_PATH {{ cmake_framework_path }})
        {% endif %}
        {% if cmake_include_path %}
        list(PREPEND CMAKE_INCLUDE_PATH {{ cmake_include_path }})
        {% endif %}
        {% if host_runtime_dirs %}
        set(RECIPE_RUNTIME_LIB_DIRS {{ host_runtime_dirs }} )
        {% endif %}

        {% if cross_building %}
        if(NOT DEFINED CMAKE_FIND_ROOT_PATH_MODE_PACKAGE OR CMAKE_FIND_ROOT_PATH_MODE_PACKAGE STREQUAL "ONLY")
            set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE "BOTH")
        endif()
        if(NOT DEFINED CMAKE_FIND_ROOT_PATH_MODE_PROGRAM OR CMAKE_FIND_ROOT_PATH_MODE_PROGRAM STREQUAL "ONLY")
            set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM "BOTH")
        endif()
        if(NOT DEFINED CMAKE_FIND_ROOT_PATH_MODE_LIBRARY OR CMAKE_FIND_ROOT_PATH_MODE_LIBRARY STREQUAL "ONLY")
            set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY "BOTH")
        endif()
        {% if is_apple %}
        if(NOT DEFINED CMAKE_FIND_ROOT_PATH_MODE_FRAMEWORK OR CMAKE_FIND_ROOT_PATH_MODE_FRAMEWORK STREQUAL "ONLY")
            set(CMAKE_FIND_ROOT_PATH_MODE_FRAMEWORK "BOTH")
        endif()
        {% endif %}
        if(NOT DEFINED CMAKE_FIND_ROOT_PATH_MODE_INCLUDE OR CMAKE_FIND_ROOT_PATH_MODE_INCLUDE STREQUAL "ONLY")
            set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE "BOTH")
        endif()
        {% endif %}
        endif()
        """)

    def _runtime_dirs_value(self, dirs: dict[str, list[str]]) -> str:
        if is_multi_configuration(self._toolchain.generator):
            return " ".join(f'"$<$<CONFIG:{c}>:{i}>"' for c, v in dirs.items() for i in v)
        else:
            return " ".join(f'"{item}"' for _, items in dirs.items() for item in items)

    def _get_host_runtime_dirs(self, host_req: list[Any]) -> dict[Any, Any]:
        settings = self._recipe.settings
        host_runtime_dirs: dict[Any, Any] = {}
        is_win = self._recipe.settings.os == "Windows"

        # Get the previous configuration
        if is_multi_configuration(self._toolchain.generator) and os.path.exists(RECIPE_TOOLCHAIN_FILENAME):
            existing_toolchain = load(RECIPE_TOOLCHAIN_FILENAME)
            pattern_lib_dirs = r"set\(RECIPE_RUNTIME_LIB_DIRS ([^)]*)\)"
            variable_match = re.search(pattern_lib_dirs, existing_toolchain)
            if variable_match:
                capture = variable_match.group(1)
                matches = re.findall(r'"\$<\$<CONFIG:([A-Za-z]*)>:([^>]*)>"', capture)
                host_runtime_dirs = {}
                for k, v in matches:
                    host_runtime_dirs.setdefault(k, []).append(v)

        # Calculate the dirs for the current build_type
        runtime_dirs: list[Any] = []
        for req in host_req:
            cppinfo = req.info.aggregated_components()
            runtime_dirs.extend(cppinfo.bindirs if is_win else cppinfo.libdirs)

        build_type = settings.build_type
        host_runtime_dirs[build_type] = [s.replace("\\", "/") for s in runtime_dirs]

        return host_runtime_dirs

    def _join_paths(self, paths: list[str]) -> str:
        paths = [p.replace("\\", "/").replace("$", "\\$").replace('"', '\\"') for p in paths]
        paths = [relativize_path(p, self._recipe, "${CMAKE_CURRENT_LIST_DIR}") for p in paths]
        return " ".join([f'"{p}"' for p in paths])

    def context(self) -> dict[str, Any] | None:
        # To find the generated cmake_find_package finders
        # TODO: Change this for parameterized output location of CMakeDeps
        find_package_prefer_config = "ON"  # assume ON by default if not specified in conf
        prefer_config = self._recipe.conf.tools.cmake.toolchain.find_package_prefer_config
        if prefer_config is False:
            find_package_prefer_config = "OFF"

        is_apple_ = is_apple_os(self._recipe)

        # Read information from host context
        # TODO: Add here in 2.0 the "skip": False trait
        host_req = self._recipe.dependencies.filter({"build": False}).values()
        build_paths: list[Any] = []
        host_lib_paths: list[Any] = []
        host_runtime_dirs = self._get_host_runtime_dirs(host_req)
        host_framework_paths: list[Any] = []
        host_include_paths: list[Any] = []
        for req in host_req:
            cppinfo = req.info.aggregated_components()
            build_paths.extend(cppinfo.builddirs)
            host_lib_paths.extend(cppinfo.libdirs)
            if is_apple_:
                host_framework_paths.extend(cppinfo.frameworkdirs)
            host_include_paths.extend(cppinfo.includedirs)

        # Read information from build context
        build_req = self._recipe.dependencies.build.values()
        build_bin_paths: list[Any] = []
        for req in build_req:
            cppinfo = req.info.aggregated_components()
            build_paths.extend(cppinfo.builddirs)
            build_bin_paths.extend(cppinfo.bindirs)

        return {
            "find_package_prefer_config": find_package_prefer_config,
            "generators_folder": "${CMAKE_CURRENT_LIST_DIR}",
            "build_paths": self._join_paths(build_paths),
            "cmake_program_path": self._join_paths(build_bin_paths),
            "cmake_library_path": self._join_paths(host_lib_paths),
            "cmake_framework_path": self._join_paths(host_framework_paths),
            "cmake_include_path": self._join_paths(host_include_paths),
            "is_apple": is_apple_,
            "cross_building": cross_building(self._recipe),
            "host_runtime_dirs": self._runtime_dirs_value(host_runtime_dirs),
        }


class PkgConfigBlock(Block):
    template = textwrap.dedent(
        """
        # Define pkg-config from 'tools.gnu:pkg_config' executable and paths

        {% if pkg_config %}
        set(PKG_CONFIG_EXECUTABLE {{ pkg_config }} CACHE FILEPATH "pkg-config executable")
        {% endif %}
        {% if pkg_config_path %}
        if (DEFINED ENV{PKG_CONFIG_PATH})
        set(ENV{PKG_CONFIG_PATH} "{{ pkg_config_path }}$ENV{PKG_CONFIG_PATH}")
        else()
        set(ENV{PKG_CONFIG_PATH} "{{ pkg_config_path }}")
        endif()
        {% endif %}
        """)

    def context(self) -> dict[str, Any] | None:
        pkg_config = self._recipe.conf.tools.gnu.pkg_config
        if pkg_config:
            pkg_config = os.fspath(pkg_config).replace("\\", "/")
        subsystem = deduce_subsystem(self._recipe, "build")
        pathsep = ":" if subsystem != WINDOWS else ";"
        pkg_config_path = "${CMAKE_CURRENT_LIST_DIR}" + pathsep
        return {
            "pkg_config": pkg_config, "pkg_config_path": pkg_config_path,
        }


class UserToolchain(Block):
    template = textwrap.dedent(
        """
        # Include one or more CMake user toolchain from tools.cmake.toolchain:user_toolchain

        {% for user_toolchain in paths %}
        message(STATUS "Recipe toolchain: Including user_toolchain: {{user_toolchain}}")
        include("{{user_toolchain}}")
        {% endfor %}
        """)

    def context(self) -> dict[str, Any] | None:
        # This is global [conf] injection of extra toolchain files
        user_toolchain = self._recipe.conf.tools.cmake.toolchain.user_toolchain
        paths = [relativize_path(os.fspath(p), self._recipe, "${CMAKE_CURRENT_LIST_DIR}") for p in user_toolchain]
        paths = [p.replace("\\", "/") for p in paths]
        return {"paths": paths}


class ExtraFlagsBlock(Block):
    """This block is adding flags directly from user [conf] section"""

    _template = textwrap.dedent(
        """
        # Include extra C++, C and linker flags from configuration tools.build:<type>flags
        # and from CMakeToolchain.extra_<type>_flags

        # Recipe conf flags start: {{config}}
        {% if cxxflags %}
        string(APPEND RECIPE_CXX_FLAGS{{suffix}} "{% for cxxflag in cxxflags %} {{ cxxflag }}{% endfor %}")
        {% endif %}
        {% if cflags %}
        string(APPEND RECIPE_C_FLAGS{{suffix}} "{% for cflag in cflags %} {{ cflag }}{% endfor %}")
        {% endif %}
        {% if sharedlinkflags %}
        string(APPEND RECIPE_SHARED_LINKER_FLAGS{{suffix}} "{% for sharedlinkflag in sharedlinkflags %} {{ sharedlinkflag }}{% endfor %}")
        {% endif %}
        {% if exelinkflags %}
        string(APPEND RECIPE_EXE_LINKER_FLAGS{{suffix}} "{% for exelinkflag in exelinkflags %} {{ exelinkflag }}{% endfor %}")
        {% endif %}
        {% if rcflags %}
        string(APPEND RECIPE_RC_FLAGS{{suffix}} "{% for rcflag in rcflags %} {{ rcflag }}{% endfor %}")
        {% endif %}
        {% if defines %}
        {% if config %}
        {% for define in defines %}
        add_compile_definitions("$<$<CONFIG:{{config}}>:{{ define }}>")
        {% endfor %}
        {% else %}
        add_compile_definitions({% for define in defines %} "{{ define }}"{% endfor %})
        {% endif %}
        {% endif %}
        # Recipe conf flags end
        """)

    @property
    def template(self) -> str:  # pyright: ignore[reportIncompatibleVariableOverride] -- dynamic template computed from existing toolchain file; base is a str class var
        if not is_multi_configuration(self._toolchain.generator):
            return self._template

        sections: dict[str, list[str]] = {}
        if os.path.exists(RECIPE_TOOLCHAIN_FILENAME):
            existing_toolchain = load(RECIPE_TOOLCHAIN_FILENAME)
            lines = existing_toolchain.splitlines()
            current_section: list[str] | None = None
            for line in lines:
                if line.startswith("# Recipe conf flags start: "):
                    section_name = line.split(":", 1)[1].strip()
                    current_section = [line]
                    sections[section_name] = current_section
                elif line == "# Recipe conf flags end":
                    assert current_section is not None
                    current_section.append(line)
                    current_section = None
                elif current_section is not None:
                    current_section.append(line)
            sections.pop("", None)  # Just in case it had a single config before

        config = self._recipe.settings.build_type
        for k, v in sections.items():
            if k != config:
                v.insert(0, "{% raw %}")
                v.append("{% endraw %}")
        sections[config] = [self._template]
        section_texts = ["\n".join(section_lines) for section_lines in sections.values()]
        return "\n".join(section_texts)

    def context(self) -> dict[str, Any] | None:
        # Now, it's time to get all the flags defined by the user
        cxxflags = self._toolchain.extra_cxxflags + self._recipe.conf.tools.build.cxxflags
        cflags = self._toolchain.extra_cflags + self._recipe.conf.tools.build.cflags
        sharedlinkflags = self._toolchain.extra_sharedlinkflags + self._recipe.conf.tools.build.sharedlinkflags
        exelinkflags = self._toolchain.extra_exelinkflags + self._recipe.conf.tools.build.exelinkflags
        rcflags = self._recipe.conf.tools.build.rcflags
        defines = self._recipe.conf.tools.build.defines

        # See upstream issue 13374
        android_ndk_path = self._recipe.conf.tools.android.ndk_path
        android_legacy_toolchain = self._recipe.conf.tools.android.cmake_legacy_toolchain
        if android_ndk_path and (cxxflags or cflags) and android_legacy_toolchain is not False:
            self._recipe.output.warning(
                "conf.tools.build.cxxflags or cflags are defined, but Android NDK toolchain may be overriding "
                "the values. Consider setting conf.tools.android.cmake_legacy_toolchain to False.")

        config = ""
        suffix = ""
        if is_multi_configuration(self._toolchain.generator):
            config = self._recipe.settings.build_type
            suffix = f"_{config.upper()}" if config else ""
        return {
            "config": config, "suffix": suffix, "cxxflags": cxxflags, "cflags": cflags, "sharedlinkflags": sharedlinkflags, "exelinkflags": exelinkflags, "rcflags": rcflags, "defines": [define.replace('"', '\\"') for define in defines],
        }


class CMakeFlagsInitBlock(Block):
    template = textwrap.dedent(
        """
        # Define CMAKE_<XXX>_FLAGS from RECIPE_<XXX>_FLAGS

        foreach(config IN LISTS CMAKE_CONFIGURATION_TYPES)
            string(TOUPPER ${config} config)
            if(DEFINED RECIPE_CXX_FLAGS_${config})
                string(APPEND CMAKE_CXX_FLAGS_${config}_INIT " ${RECIPE_CXX_FLAGS_${config}}")
            endif()
            if(DEFINED RECIPE_C_FLAGS_${config})
                string(APPEND CMAKE_C_FLAGS_${config}_INIT " ${RECIPE_C_FLAGS_${config}}")
            endif()
            if(DEFINED RECIPE_SHARED_LINKER_FLAGS_${config})
                string(APPEND CMAKE_SHARED_LINKER_FLAGS_${config}_INIT " ${RECIPE_SHARED_LINKER_FLAGS_${config}}")
            endif()
            if(DEFINED RECIPE_EXE_LINKER_FLAGS_${config})
                string(APPEND CMAKE_EXE_LINKER_FLAGS_${config}_INIT " ${RECIPE_EXE_LINKER_FLAGS_${config}}")
            endif()
            if(DEFINED RECIPE_RC_FLAGS_${config})
                string(APPEND CMAKE_RC_FLAGS_${config}_INIT " ${RECIPE_RC_FLAGS_${config}}")
            endif()
        endforeach()

        if(DEFINED RECIPE_CXX_FLAGS)
            string(APPEND CMAKE_CXX_FLAGS_INIT " ${RECIPE_CXX_FLAGS}")
        endif()
        if(DEFINED RECIPE_C_FLAGS)
            string(APPEND CMAKE_C_FLAGS_INIT " ${RECIPE_C_FLAGS}")
        endif()
        if(DEFINED RECIPE_SHARED_LINKER_FLAGS)
            string(APPEND CMAKE_SHARED_LINKER_FLAGS_INIT " ${RECIPE_SHARED_LINKER_FLAGS}")
        endif()
        if(DEFINED RECIPE_EXE_LINKER_FLAGS)
            string(APPEND CMAKE_EXE_LINKER_FLAGS_INIT " ${RECIPE_EXE_LINKER_FLAGS}")
        endif()
        if(DEFINED RECIPE_RC_FLAGS)
            string(APPEND CMAKE_RC_FLAGS_INIT " ${RECIPE_RC_FLAGS}")
        endif()
        if(DEFINED RECIPE_OBJCXX_FLAGS)
            string(APPEND CMAKE_OBJCXX_FLAGS_INIT " ${RECIPE_OBJCXX_FLAGS}")
        endif()
        if(DEFINED RECIPE_OBJC_FLAGS)
            string(APPEND CMAKE_OBJC_FLAGS_INIT " ${RECIPE_OBJC_FLAGS}")
        endif()
        """)


class TryCompileBlock(Block):
    template = textwrap.dedent(
        """
        # Blocks after this one will not be added when running CMake try/checks
        {% if config %}
        if(NOT DEFINED CMAKE_TRY_COMPILE_CONFIGURATION)  # to allow user command line override
            set(CMAKE_TRY_COMPILE_CONFIGURATION {{config}})
        endif()
        {% endif %}
        get_property( _CMAKE_IN_TRY_COMPILE GLOBAL PROPERTY IN_TRY_COMPILE )
        if(_CMAKE_IN_TRY_COMPILE)
            message(STATUS "Running toolchain IN_TRY_COMPILE")
            return()
        endif()
        """)

    def context(self) -> dict[str, Any] | None:
        # Only for well known CMake configurations, but not for custom ones
        # Revert of upstream PR 18559, even if it was correct, there are
        # legacy code using check_function_exists that breaks in CMake with MSVC, see
        # upstream issue 18689
        # TODO: Resume this effort when other try_compile things are sorted out
        # bt = self._recipe.settings.build_type
        # config = bt if bt in ["Debug", "Release", "RelWithDebInfo", "MinSizeRel"] else None
        config = None  # Keep it defined but as `None` in case some user already customized it
        return {"config": config}


class CompilersBlock(Block):
    template = textwrap.dedent(
        r"""
        {% for lang, compiler_path in compilers.items() %}
        set(CMAKE_{{ lang }}_COMPILER "{{ compiler_path|replace('\\', '/') }}")
        {% endfor %}
        """)

    def context(self) -> dict[str, Any] | None:
        compilers_by_conf = self._recipe.conf.tools.build.compiler_executables
        # Map the possible languages
        compilers = {}
        # Allowed <LANG> variables (and <LANG>_LAUNCHER)
        compilers_mapping = {
            "c": "C", "cuda": "CUDA", "cpp": "CXX", "objc": "OBJC", "objcpp": "OBJCXX", "rc": "RC", "fortran": "Fortran", "asm": "ASM", "hip": "HIP", "ispc": "ISPC",
        }
        for comp, lang in compilers_mapping.items():
            # To set CMAKE_<LANG>_COMPILER
            if comp in compilers_by_conf:
                compilers[lang] = compilers_by_conf[comp]
        compiler = self._recipe.settings.compiler
        if compiler == "msvc" and "Ninja" in str(self._toolchain.generator):
            # None of them defined, if one is defined by user, user should define the other too
            if "c" not in compilers_by_conf and "cpp" not in compilers_by_conf:
                compilers["C"] = "cl"
                compilers["CXX"] = "cl"
        return {"compilers": compilers}


class GenericSystemBlock(Block):
    template = textwrap.dedent(
        """
        # Definition of system, platform and toolset

        {% if cmake_sysroot %}
        set(CMAKE_SYSROOT {{ cmake_sysroot }})
        {% endif %}
        {% if cmake_system_name %}
        # Cross building
        if(NOT DEFINED CMAKE_SYSTEM_NAME) # It might have been defined by a user toolchain
        set(CMAKE_SYSTEM_NAME {{ cmake_system_name }})
        endif()
        {% endif %}
        {% if cmake_system_version %}
        if(NOT DEFINED CMAKE_SYSTEM_VERSION) # It might have been defined by a user toolchain
        set(CMAKE_SYSTEM_VERSION {{ cmake_system_version }})
        endif()
        {% endif %}
        {% if cmake_system_processor %}
        if(NOT DEFINED CMAKE_SYSTEM_PROCESSOR) # It might have been defined by a user toolchain
        set(CMAKE_SYSTEM_PROCESSOR {{ cmake_system_processor }})
        endif()
        {% endif %}

        {% if generator_platform and not winsdk_version %}
        set(CMAKE_GENERATOR_PLATFORM "{{ generator_platform }}" CACHE STRING "" FORCE)
        {% elif winsdk_version %}
        if(POLICY CMP0149)
            cmake_policy(GET CMP0149 _POLICY_WINSDK_VERSION)
        endif()
        if(_POLICY_WINSDK_VERSION STREQUAL "NEW")
            message(STATUS "Recipe toolchain: CMAKE_GENERATOR_PLATFORM={{gen_platform_sdk_version}}")
            set(CMAKE_GENERATOR_PLATFORM "{{ gen_platform_sdk_version }}" CACHE STRING "" FORCE)
        else()
            # winsdk_version will be taken from above CMAKE_SYSTEM_VERSION
            message(STATUS "Recipe toolchain: CMAKE_GENERATOR_PLATFORM={{generator_platform}}")
            set(CMAKE_GENERATOR_PLATFORM "{{ generator_platform }}" CACHE STRING "" FORCE)
        endif()
        {% endif %}

        {% if toolset %}
        message(STATUS "Recipe toolchain: CMAKE_GENERATOR_TOOLSET={{ toolset }}")
        set(CMAKE_GENERATOR_TOOLSET "{{ toolset }}" CACHE STRING "" FORCE)
        {% endif %}
        """)

    @staticmethod
    def get_toolset(generator: str | None, recipe: RecipeBase) -> str | None:
        toolset = None
        if generator is None or ("Visual" not in generator and "Xcode" not in generator):
            return None
        settings = recipe.settings
        compiler = settings.compiler
        if compiler == "msvc":
            toolset = settings.compiler_toolset
            if toolset is None:
                compiler_version = str(settings.compiler_version)
                msvc_update = recipe.conf.tools.microsoft.msvc_update
                compiler_update = msvc_update or settings.compiler_update
                toolset = msvc_version_to_toolset_version(compiler_version)
                if compiler_update is not None:  # It is full one(19.28), not generic 19.2X
                    # The equivalent of compiler 19.26 is toolset 14.26
                    toolset = cast(str, toolset) + f",version=14.{compiler_version[-1]}{compiler_update}"
        elif compiler == "clang":
            if generator and "Visual" in generator:
                if any(f"Visual Studio {v}" in generator for v in ("16", "17", "18")):
                    toolset = "ClangCL"
                else:
                    raise RecipeException(
                        "CMakeToolchain with compiler=clang and a CMake "
                        "'Visual Studio' generator requires VS16, VS17 or VS18")
        toolset_arch = recipe.conf.tools.cmake.toolchain.toolset_arch
        if toolset_arch is not None:
            toolset_arch = f"host={toolset_arch}"
            toolset = toolset_arch if toolset is None else f"{toolset},{toolset_arch}"
        toolset_cuda = recipe.conf.tools.cmake.toolchain.toolset_cuda
        if toolset_cuda is not None:
            toolset_cuda = relativize_path(os.fspath(toolset_cuda), recipe, "${CMAKE_CURRENT_LIST_DIR}")
            toolset_cuda = f"cuda={toolset_cuda}"
            toolset = toolset_cuda if toolset is None else f"{toolset},{toolset_cuda}"
        return toolset

    @staticmethod
    def get_generator_platform(generator: str | None, recipe: RecipeBase) -> str | None:
        settings = recipe.settings
        # Returns the generator platform to be used by CMake
        compiler = settings.compiler
        arch = settings.arch

        if compiler in ("msvc", "clang") and generator and "Visual" in generator:
            return msvc_platform_from_arch(arch)
        return None

    def _get_generic_system_name(self):
        os_host = self._recipe.settings.os
        os_build = self._recipe.settings_build.os
        arch_host = self._recipe.settings.arch
        arch_build = self._recipe.settings_build.arch
        cmake_system_name_map = {
            "Neutrino": "QNX", "": "Generic", "baremetal": "Generic", None: "Generic",
        }
        if os_host != os_build:
            # os_host would be 'baremetal' for tricore, but it's ideal to use the Generic-ELF
            # system name instead of just "Generic" because it matches how Aurix Dev Studio
            # generated makefiles behave by generating binaries with the '.elf' extension.
            if arch_host in ["tc131", "tc16", "tc161", "tc162", "tc18"]:
                return "Generic-ELF"
            return cmake_system_name_map.get(os_host, os_host)
        elif arch_host is not None and arch_host != arch_build:  # pyright: ignore[reportUnnecessaryComparison] -- defensive: arch declared str but may be unset at runtime
            return cmake_system_name_map.get(os_host, os_host)

    def _is_apple_cross_building(self):
        os_host = self._recipe.settings.os
        arch_host = self._recipe.settings.arch
        arch_build = self._recipe.settings_build.arch
        os_build = self._recipe.settings_build.os
        return os_host in ("iOS", "tvOS", "visionOS") or (os_host == "Mac" and (arch_host != arch_build or os_build != os_host))

    @staticmethod
    def _get_darwin_version(os_name: str, os_version: str):
        # version mapping from https://en.wikipedia.org/wiki/Darwin_(operating_system)
        # but a more detailed version can be found in https://theapplewiki.com/wiki/Kernel
        version_mapping = {
            "Mac": {
                "10.6": "10", "10.7": "11", "10.8": "12", "10.9": "13", "10.10": "14", "10.11": "15", "10.12": "16", "10.13": "17", "10.14": "18", "10.15": "19", "11": "20", "12": "21", "13": "22", "14": "23", "15": "24", "26": "25",
            }, "iOS": {
                "7": "14", "8": "14", "9": "15", "10": "16", "11": "17", "12": "18", "13": "19", "14": "20", "15": "21", "16": "22", "17": "23", "18": "24", "26": "25",
            }, "tvOS": {
                "11": "17", "12": "18", "13": "19", "14": "20", "15": "21", "16": "22", "17": "23", "18": "24", "26": "25",
            }, "visionOS": {
                "1": "23", "2": "24", "26": "25",
            },
        }
        darwin_version = Version(os_version).major if os_name != "Mac" or (os_name == "Mac" and Version(
            os_version) >= Version("11")) else os_version
        return version_mapping.get(os_name, {}).get(str(darwin_version))

    def _get_cross_build(self):
        system_name = self._recipe.conf.tools.cmake.toolchain.system_name
        system_version = self._recipe.conf.tools.cmake.toolchain.system_version
        system_processor = self._recipe.conf.tools.cmake.toolchain.system_processor

        # try to detect automatically
        os_host = self._recipe.settings.os
        os_host_version = self._recipe.settings.os_version
        arch_host = self._recipe.settings.arch
        if arch_host == "ARM":
            arch_host = {"Windows": "ARM64", "Mac": "arm64"}.get(os_host, "aarch64")

        if system_name is None:  # Try to deduce
            _system_version = None
            _system_processor = None
            if self._is_apple_cross_building():
                # cross-build in Macos also for M1
                system_name = {"Mac": "Darwin"}.get(os_host, os_host)
                #  CMAKE_SYSTEM_VERSION for Apple sets the Darwin version, not the os version
                _system_version = self._get_darwin_version(os_host, cast(str, os_host_version))
                _system_processor = to_apple_arch(self._recipe)
            elif os_host != "Android":
                system_name = self._get_generic_system_name()
                if arch_host in ["tc131", "tc16", "tc161", "tc162", "tc18"]:
                    _system_processor = "tricore"
                else:
                    _system_processor = arch_host
                _system_version = os_host_version

            if system_name is not None and system_version is None:
                system_version = _system_version
            if system_name is not None and system_processor is None:
                system_processor = _system_processor

        return system_name, system_version, system_processor

    def _get_winsdk_version(self, system_version: str | None, generator_platform: str | None):
        compiler = self._recipe.settings.compiler
        if compiler not in ("msvc", "clang") or "Visual" not in str(self._toolchain.generator):
            # Ninja will get it from VCVars, not from toolchain
            return system_version, None, None

        winsdk_version = self._recipe.conf.tools.microsoft.winsdk_version
        if winsdk_version:
            if system_version:
                self._recipe.output.warning(
                    "Both cmake_system_version and winsdk_version confs"
                    " defined, prioritizing winsdk_version")
            system_version = winsdk_version
        elif "Windows" in (self._recipe.settings.os or ""):
            winsdk_version = self._recipe.settings.os_version
            if system_version:
                if winsdk_version:
                    self._recipe.output.warning(
                        "Both cmake_system_version conf and os.version"
                        " defined, prioritizing cmake_system_version")
                winsdk_version = system_version

        gen_platform_sdk_version = [
            generator_platform, f"version={winsdk_version}" if winsdk_version else None,
        ]
        gen_platform_sdk_version = ",".join(d for d in gen_platform_sdk_version if d)

        return system_version, winsdk_version, gen_platform_sdk_version

    def context(self) -> dict[str, Any] | None:
        generator = self._toolchain.generator
        generator_platform = self.get_generator_platform(generator, self._recipe)
        toolset = self.get_toolset(generator, self._recipe)
        system_name, system_version, system_processor = self._get_cross_build()

        # This is handled by the tools.apple:sdk_path and CMAKE_OSX_SYSROOT in Apple
        cmake_sysroot = self._recipe.conf.tools.build.sysroot
        cmake_sysroot = os.fspath(cmake_sysroot).replace("\\", "/") if cmake_sysroot is not None else None
        if cmake_sysroot is not None:
            cmake_sysroot = relativize_path(
                cmake_sysroot, self._recipe, "${CMAKE_CURRENT_LIST_DIR}")

        result = self._get_winsdk_version(system_version, generator_platform)
        system_version, winsdk_version, gen_platform_sdk_version = result

        return {
            "toolset": toolset,
            "generator_platform": generator_platform,
            "cmake_system_name": system_name,
            "cmake_system_version": system_version,
            "cmake_system_processor": system_processor,
            "cmake_sysroot": cmake_sysroot,
            "winsdk_version": winsdk_version,
            "gen_platform_sdk_version": gen_platform_sdk_version,
        }


class ExtraVariablesBlock(Block):
    template = textwrap.dedent(
        """
        # Definition of extra CMake variables from tools.cmake.toolchain:extra_variables

        {% if extra_variables %}
        {% for key, value in extra_variables.items() %}
        set({{ key }} {{ value }})
        {% endfor %}
        {% endif %}
        """)

    def context(self) -> dict[str, Any] | None:
        from thirdparty.cmake.utils import parse_extra_variable
        extra_variables = self._recipe.conf.tools.cmake.toolchain.extra_variables
        compilation_verbose = self._recipe.conf.tools.compilation.verbose
        build_log_level = "VERBOSE" if self._recipe.conf.tools.build.verbose else "ERROR"

        if compilation_verbose:
            extra_variables.setdefault(
                "CMAKE_VERBOSE_MAKEFILE", {
                    "cache": True, "type": "BOOL", "value": "ON",
                })

        extra_variables.setdefault(
            "CMAKE_MESSAGE_LOG_LEVEL", {
                "cache": True, "type": "STRING", "value": build_log_level,
            })

        # Silence the per-file "-- Installing: <path>" spam from cmake --install unless verbose
        # (default is ALWAYS); projects with many files otherwise flood the log.
        extra_variables.setdefault(
            "CMAKE_INSTALL_MESSAGE", {
                "cache": True, "type": "STRING", "value": "ALWAYS" if compilation_verbose else "NEVER",
            })

        parsed_extra_variables = {}
        for key, value in extra_variables.items():
            parsed_extra_variables[key] = parse_extra_variable(
                "conf.tools.cmake.toolchain.extra_variables", key, value)
        return {"extra_variables": parsed_extra_variables}


class OutputDirsBlock(Block):
    @property
    def template(self) -> str:  # pyright: ignore[reportIncompatibleVariableOverride] -- dynamic template; base is a str class var
        return textwrap.dedent(
            """
            # Definition of CMAKE_INSTALL_XXX folders

            # Ensure export(PACKAGE) honors CMAKE_EXPORT_PACKAGE_REGISTRY even if the
            # project sets cmake_minimum_required() lower than 3.15.
            cmake_policy(SET CMP0090 NEW)
            if(NOT DEFINED CMAKE_EXPORT_PACKAGE_REGISTRY)
                set(CMAKE_EXPORT_PACKAGE_REGISTRY OFF)
            endif()

            {% if package_folder %}
            set(CMAKE_INSTALL_PREFIX "{{package_folder}}")
            {% endif %}
            {% if default_bin %}
            set(CMAKE_INSTALL_BINDIR "{{default_bin}}")
            set(CMAKE_INSTALL_SBINDIR "{{default_bin}}")
            set(CMAKE_INSTALL_LIBEXECDIR "{{default_bin}}")
            {% endif %}
            {% if default_lib %}
            set(CMAKE_INSTALL_LIBDIR "{{default_lib}}")
            {% endif %}
            {% if default_include %}
            set(CMAKE_INSTALL_INCLUDEDIR "{{default_include}}")
            set(CMAKE_INSTALL_OLDINCLUDEDIR "{{default_include}}")
            {% endif %}
            {% if default_res %}
            set(CMAKE_INSTALL_DATAROOTDIR "{{default_res}}")
            {% endif %}
            """)

    def _get_cpp_info_value(self, name: str):
        # These variables are used by "cmake install" and therefore refer to the package
        # layout, even when the root path comes from the build directory.
        elements = getattr(self._recipe.info, name)
        return elements[0] if elements else None

    def context(self) -> dict[str, Any] | None:
        pf = self._recipe.folders.package
        return {
            "package_folder": pf.as_posix() if pf else None,
            "default_bin": self._get_cpp_info_value("bindirs"),
            "default_lib": self._get_cpp_info_value("libdirs"),
            "default_include": self._get_cpp_info_value("includedirs"),
            "default_res": self._get_cpp_info_value("resdirs"),
        }


class VariablesBlock(Block):
    @property
    def template(self) -> str:  # pyright: ignore[reportIncompatibleVariableOverride] -- dynamic template; base is a str class var
        return textwrap.dedent(
            """
            # Definition of CMake variables from CMakeToolchain.variables values

            {% macro iterate_configs(var_config, action) %}
            {% for it, values in var_config.items() %}
                {% set genexpr = namespace(str='') %}
                {% for conf, value in values -%}
                set(RECIPE_DEF_{{ conf }}{{ it }} "{{ value }}")
                {% endfor %}
                {% for conf, value in values -%}
                    {% set genexpr.str = genexpr.str +
                                            '$<IF:$<CONFIG:' + conf + '>,${RECIPE_DEF_' + conf|string + it|string + '},' %}
                    {% if loop.last %}{% set genexpr.str = genexpr.str + '""' -%}{%- endif -%}
                {% endfor %}
                {% for i in range(values|count) %}{% set genexpr.str = genexpr.str + '>' %}
                {% endfor %}
            set({{ it }} {{ genexpr.str }} CACHE STRING
                "Variable {{ it }} recipe-toolchain defined")
            {% endfor %}
            {% endmacro %}
            # Variables
            {% for it, value in variables.items() %}
            {% if value is boolean %}
            set({{ it }} {{ "ON" if value else "OFF"}} CACHE BOOL "Variable {{ it }} recipe-toolchain defined")
            {% else %}
            set({{ it }} "{{ value }}" CACHE STRING "Variable {{ it }} recipe-toolchain defined")
            {% endif %}
            {% endfor %}
            # Variables  per configuration
            {{ iterate_configs(variables_config, action='set') }}
            """)

    def context(self) -> dict[str, Any] | None:
        return {
            "variables": self._toolchain.variables, "variables_config": self._toolchain.variables.configuration_types,
        }


class PreprocessorBlock(Block):
    @property
    def template(self) -> str:  # pyright: ignore[reportIncompatibleVariableOverride] -- dynamic template; base is a str class var
        return textwrap.dedent(
            """
            # Preprocessor definitions from CMakeToolchain.preprocessor_definitions values
    
            {% for it, value in preprocessor_definitions.items() %}
            {% if value is none %}
            add_compile_definitions("{{ it }}")
            {% else %}
            add_compile_definitions("{{ it }}={{ value }}")
            {% endif %}
            {% endfor %}
            # Preprocessor definitions per configuration
            {% for name, values in preprocessor_definitions_config.items() %}
            {%- for (conf, value) in values %}
            {% if value is none %}
            set(RECIPE_DEF_{{conf}}_{{name}} "{{name}}")
            {% else %}
            set(RECIPE_DEF_{{conf}}_{{name}} "{{name}}={{value}}")
            {% endif %}
            {% endfor %}
            add_compile_definitions(
            {%- for (conf, value) in values %}
            $<$<CONFIG:{{conf}}>:${RECIPE_DEF_{{conf}}_{{name}}}>
            {%- endfor -%})
            {% endfor %}
            """)

    def context(self) -> dict[str, Any] | None:
        return {
            "preprocessor_definitions": self._toolchain.preprocessor_definitions, "preprocessor_definitions_config": self._toolchain.preprocessor_definitions.configuration_types,
        }


class WarningFilterBlock(Block):
    """Strip project-set MSVC warning-level flags so the quiet ``/w`` wins without D9025.

    When building quietly we inject ``-w`` (== ``/w``) to silence warnings, but any ``/W0-4``
    or ``/Wall`` a project passes to ``add_compile_options``/``target_compile_options`` collides
    with it and makes cl spam ``D9025: overriding '/w' with '/W3'`` once per file (and the
    project flag wins, so warnings show anyway).  Redefining those two commands here - before
    ``project()`` - to drop plain warning-level args lets ``/w`` take effect cleanly.  Verbose
    builds skip this block so warnings are shown.

    Only *plain* whole-argument warning flags are dropped; generator expressions are preserved
    intact (iterating ``ARGV`` by index and re-escaping ``;`` avoids splitting a multi-element
    genex like ``$<$<COMPILER_ID:GNU>:-Wall;-Wextra>`` and leaking ``-Wextra`` to cl).  A genex
    that hard-codes ``/W4`` for MSVC therefore still slips through and is handled per-recipe.
    """

    @property
    def template(self) -> str:  # pyright: ignore[reportIncompatibleVariableOverride] -- dynamic template; base is a str class var
        return textwrap.dedent(
            """
            function(add_compile_options)
                set(_recipe_filtered "")
                set(_recipe_i 0)
                while(_recipe_i LESS ${ARGC})
                    set(_recipe_opt "${ARGV${_recipe_i}}")
                    if(NOT "${_recipe_opt}" MATCHES "^[-/]W([0-4]|all)$")
                        string(REPLACE ";" "\\;" _recipe_opt "${_recipe_opt}")
                        list(APPEND _recipe_filtered "${_recipe_opt}")
                    endif()
                    math(EXPR _recipe_i "${_recipe_i} + 1")
                endwhile()
                _add_compile_options(${_recipe_filtered})
            endfunction()

            function(target_compile_options)
                set(_recipe_filtered "")
                set(_recipe_i 0)
                while(_recipe_i LESS ${ARGC})
                    set(_recipe_opt "${ARGV${_recipe_i}}")
                    if(NOT "${_recipe_opt}" MATCHES "^[-/]W([0-4]|all)$")
                        string(REPLACE ";" "\\;" _recipe_opt "${_recipe_opt}")
                        list(APPEND _recipe_filtered "${_recipe_opt}")
                    endif()
                    math(EXPR _recipe_i "${_recipe_i} + 1")
                endwhile()
                _target_compile_options(${_recipe_filtered})
            endfunction()
            """)

    def context(self) -> dict[str, Any] | None:
        # Only when quiet: verbose builds want the project's warnings shown.
        if self._recipe.conf.tools.compilation.verbose:
            return None
        return {}


class ToolchainBlocks:
    def __init__(
        self,
        recipe: RecipeBase,
        toolchain: Any,
        items: Any = None):
        self._blocks: dict[str, Block] = {}
        self._recipe = recipe
        self._toolchain = toolchain
        if items:
            for name, block in items:
                self._blocks[name] = block(recipe, toolchain, name)

    def keys(self):
        return self._blocks.keys()

    def items(self):
        return self._blocks.items()

    def remove(self, name: str, *args: str):
        del self._blocks[name]
        for arg in args:
            del self._blocks[arg]

    def enabled(self, name: str, *args: str):
        """
        keep the blocks provided as arguments, remove the others
        """
        to_keep = [name] + list(args)
        self._blocks = {k: v for k, v in self._blocks.items() if k in to_keep}

    def __setitem__(self, name: str, block_type: Any):
        # Create a new class inheriting Block with the elements of the provided one
        block_type = type("proxyUserBlock", (Block,), dict(block_type.__dict__))
        self._blocks[name] = block_type(self._recipe, self._toolchain, name)

    def __getitem__(self, name: str):
        return self._blocks[name]

    def process_blocks(self) -> list[str]:
        blocks = self._recipe.conf.tools.cmake.toolchain.enabled_blocks
        if blocks:
            try:
                new_blocks = {b: self._blocks[b] for b in blocks}
            except KeyError as e:
                raise RecipeException(
                    f"Block {e} defined in tools.cmake.toolchain"
                    f":enabled_blocks doesn't exist in {list(self._blocks.keys())}")
            self._blocks = new_blocks
        result: list[str] = []
        for b in self._blocks.values():
            content = b.get_rendered_content()
            if content:
                result.append(content)
        return result
