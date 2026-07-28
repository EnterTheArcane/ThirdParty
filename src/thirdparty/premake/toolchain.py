import jinja2
import os
import textwrap
from pathlib import Path
from typing import Any, cast

from thirdparty._internal.model.toolchain import find_toolchain
from thirdparty.apple.utils import apple_min_version_flag, is_apple_os, resolve_apple_flags
from thirdparty.build.cross_building import cross_building
from thirdparty.build.flags import architecture_flag, architecture_link_flag, libcxx_flags, threads_flags
from thirdparty.env.virtualbuildenv import VirtualBuildEnv
from thirdparty.files import save
from thirdparty.premake.deps import PREMAKE_ROOT_FILE
from thirdparty.recipe import RecipeBase


def _generate_flags(self: Any, recipe: RecipeBase) -> str:
    template = textwrap.dedent(
        """
        {% if extra_cflags %}
        -- C flags retrieved from CFLAGS environment, thirdparty.conf(tools.build:cflags), extra_cflags and compiler settings
        filter { files { "**.c" } }
            buildoptions { {{ extra_cflags }} }
        filter {}
        {% endif %}
        {% if extra_cxxflags %}
        -- CXX flags retrieved from CXXFLAGS environment, thirdparty.conf(tools.build:cxxflags), extra_cxxflags and compiler settings
        filter { files { "**.cpp", "**.cxx", "**.cc" } }
            buildoptions { {{ extra_cxxflags }} }
        filter {}
        {% endif %}
        {% if extra_ldflags %}
        -- Link flags retrieved from LDFLAGS environment, thirdparty.conf(tools.build:sharedlinkflags), thirdparty.conf(tools.build:exelinkflags), extra_cxxflags and compiler settings
        linkoptions { {{ extra_ldflags }} }
        {% endif %}
        {% if extra_rcflags %}
        -- RC flags retrieved from thirdparty.conf(tools.build:rcflags)
        filter { files { "**.rc" } }
            buildoptions { {{ extra_rcflags }} }
        filter {}
        {% endif %}
        {% if extra_defines %}
        -- Defines retrieved from DEFINES environment, thirdparty.conf(tools.build:defines) and extra_defines
        defines { {{ extra_defines }} }
        {% endif %}
        """)

    def format_list(items: Any) -> str | None:
        return ", ".join(f'"{item}"' for item in items) if items else None

    def to_list(value: Any) -> list[Any]:
        return cast(list[Any], value) if isinstance(value, list) else [value] if value else []

    arch_flags = to_list(architecture_flag(self._recipe))
    cxx_flags, libcxx_compile_definitions = libcxx_flags(self._recipe)
    arch_link_flags = to_list(architecture_link_flag(self._recipe))
    thread_flags_list = threads_flags(self._recipe)

    extra_defines = format_list(
        recipe.conf.tools.build.defines + self.extra_defines + to_list(libcxx_compile_definitions))
    extra_c_flags = format_list(
        recipe.conf.tools.build.cflags + self.extra_cflags + arch_flags + thread_flags_list)
    extra_cxx_flags = format_list(
        recipe.conf.tools.build.cxxflags + to_list(cxx_flags) + self.extra_cxxflags + arch_flags + thread_flags_list)
    extra_ld_flags = format_list(
        recipe.conf.tools.build.sharedlinkflags + recipe.conf.tools.build.exelinkflags + self.extra_ldflags + arch_flags + arch_link_flags + thread_flags_list)
    extra_rc_flags = format_list(recipe.conf.tools.build.rcflags)

    return (jinja2.Template(template, trim_blocks=True, lstrip_blocks=True).render(
        extra_defines=extra_defines, extra_cflags=extra_c_flags, extra_cxxflags=extra_cxx_flags, extra_ldflags=extra_ld_flags, extra_rcflags=extra_rc_flags, ).strip())


class _PremakeProject:
    _premake_project_template = textwrap.dedent(
        """
        project "{{ name }}"
            {% if kind %}
            kind "{{ kind }}"
            {% endif %}
            {% if flags %}
        {{ flags | indent(indent_level, first=True) }}
            {% endif %}
        """)

    def __init__(self, name: str, recipe: RecipeBase) -> None:
        self.name = name
        self.kind = None
        self.extra_cxxflags = []
        self.extra_cflags = []
        self.extra_ldflags = []
        self.extra_defines = []
        self.disable = False
        self._recipe = recipe

    def _generate(self):
        """Generates project block"""
        flags_content = _generate_flags(self, self._recipe)  # Generate flags specific to this project
        return jinja2.Template(self._premake_project_template, trim_blocks=True, lstrip_blocks=True).render(
            name=self.name, kind="None" if self.disable else self.kind, flags=flags_content, indent_level=4, )


class PremakeToolchain:
    """
    PremakeToolchain generator
    """

    filename = "recipe_toolchain.premake5.lua"
    # Keep template indented correctly for Lua output
    _premake_file_template = textwrap.dedent(
        """
        #!lua
        -- Recipe auto-generated toolchain file
        {% if has_recipe_deps %}
        -- Include recipe_deps.premake5.lua with Recipe dependency setup
        include("recipe_deps.premake5.lua")
        {% endif %}

        -- Base build directory
        local locationDir = path.normalize("{{ build_folder }}")

        -- Generate workspace configurations
        for wks in premake.global.eachWorkspace() do
            workspace(wks.name)
                -- Set base location for all workspaces
                location(locationDir)
                targetdir(path.join(locationDir, "bin"))
                objdir(path.join(locationDir, "obj"))

                {% if cppstd %}
                cppdialect "{{ cppstd }}"
                {% endif %}
                {% if cstd %}
                cdialect "{{ cstd }}"
                {% endif %}
                {% if shared != None %}
                -- IMPORTANT: this global setting will only apply `project`s which do not have `kind` set.
                -- IMPORTANT: This will not override existing `kind` set in `project` block.
                -- To let recipe take control over `kind` of the libraries, DO NOT SET `kind` (StaticLib or
                -- SharedLib) in `project` block.
                kind "{{ "SharedLib" if shared else "StaticLib" }}"
                {% endif %}
                {% if pic != None %}
                -- Enable position independent code
                pic "{{ "On" if pic else "Off" }}"
                {% endif %}
                filter { "architecture: not wasm64" }
                    -- TODO: There is an issue with premake and "wasm64" when system is declared "emscripten"
                    system "{{ target_build_os }}"
                filter {}
                {% if macho_to_amd64 %}
                -- TODO: this should be fixed by premake: https://github.com/premake/premake-core/issues/2136
                buildoptions "-arch x86_64"
                linkoptions "-arch x86_64"
                {% endif %}
                {% if target_build_os == "emscripten" %}
                filter { "system:emscripten", "kind:ConsoleApp or WindowedApp" }
                    -- Replace built in .wasm extension to .js to generate also a JavaScript files
                    targetextension ".js"
                filter {}
                {% endif %}
                {% if flags %}
        {{ flags | indent(indent_level, first=True) }}
                {% endif %}

                filter { "system:macosx" }
                    -- SHARED LIBS
                    -- In the future we could add an opt in configuration to run
                    -- fix_apple_shared_install_name on executables to have a similar behavior as CMake
                    -- generator. Premake does not allow adding absolute RCPATHS
                    -- Due to this limitation, if a consumer depends on a premake shared recipe, it will
                    -- require to run runenv script to setup proper DYLD_LIBRARY_PATH
                    -- Reference: https://github.com/premake/premake-core/issues/2262#issuecomment-2378250385
                    linkoptions { "-Wl,-rpath,@loader_path" }
                filter {}

                recipe_setup()
        end

            {% for project in projects.values() %}

        {{ project._generate() }}
            {% endfor %}
        """)

    def __init__(self, recipe: RecipeBase):
        """
        :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
        """
        self._recipe = recipe
        self._projects: dict[str, _PremakeProject] = {}
        # Extra flags
        #: List of extra ``CXX`` flags. Added to ``buildoptions``.
        self.extra_cxxflags = []
        #: List of extra ``C`` flags. Added to ``buildoptions``.
        self.extra_cflags = []
        #: List of extra linker flags. Added to ``linkoptions``.
        self.extra_ldflags = []
        #: List of extra preprocessor definitions. Added to ``defines``.
        self.extra_defines = []

    @property
    def _apple_sdk_flags(self) -> list[str]:
        """The Apple SDK selection, for CFLAGS/CXXFLAGS/LDFLAGS.

        Premake emits no SDK selection of its own, so a recipe-provided clang (the llvm
        package) resolves none of the platform headers and dies inside libc++ with "We
        don't know how to get the definition of mbstate_t on your platform". Only Apple's
        own driver infers a sysroot. The architecture is left alone - premake already
        drives that through its own ``architecture``/``macho_to_amd64`` handling.
        """
        recipe = self._recipe
        if not is_apple_os(recipe):
            return []
        _min_flag, _arch_flag, isysroot_flag = resolve_apple_flags(
            recipe, is_cross_building=cross_building(recipe))
        if not isysroot_flag:
            _tc = find_toolchain(recipe)
            if _tc is not None and _tc.apple_sysroot:
                isysroot_flag = f"-isysroot {_tc.apple_sysroot}"
        return (isysroot_flag or "").split() + apple_min_version_flag(recipe).split()

    def project(self, project_name: str) -> "_PremakeProject":
        """
        The returned object will also have the same properties as the workspace but will only affect
        the project with the name.
        :param project_name: The name of the project inside the workspace to be updated.
        :return: ``<PremakeProject>`` object which allow to set project specific flags.
        """
        if project_name not in self._projects:
            self._projects[project_name] = _PremakeProject(project_name, self._recipe)
        return self._projects[project_name]

    def generate(self):
        """
        Creates a ``recipe_toolchain.premake5.lua`` file which will properly configure build paths,
        binary paths, configuration settings and compiler/linker flags based on toolchain
        configuration.
        """
        premake_recipe_deps = Path(self._recipe.folders.generators) / PREMAKE_ROOT_FILE
        cppstd = self._recipe.settings.compiler_cxx_standard
        if cppstd:
            # See premake possible cppstd values: https://premake.github.io/docs/cppdialect/
            if cppstd.startswith("gnu"):
                cppstd = f"gnu++{cppstd[3:]}"
            elif cppstd[0].isnumeric():
                cppstd = f"c++{cppstd}"

        # One VirtualBuildEnv for the whole method: each instance re-derives its environment
        # from scratch, so a second one generated later would overwrite the script and drop
        # everything set here.
        build_env = VirtualBuildEnv(self._recipe)
        env = build_env.environment()
        compilers_build_mapping = self._recipe.conf.tools.build.compiler_executables
        if compilers_build_mapping:
            if "c" in compilers_build_mapping:
                env.define("CC", cast(str, compilers_build_mapping["c"]))
            if "cpp" in compilers_build_mapping:
                env.define("CXX", cast(str, compilers_build_mapping["cpp"]))
        # The SDK flags ride the environment rather than workspace ``buildoptions``: gmake2
        # folds $(CFLAGS)/$(CXXFLAGS)/$(LDFLAGS) into every project's ALL_*FLAGS, whereas
        # workspace-level options are dropped by projects that declare their own
        # configurations (rive-runtime does).
        apple_flags = self._apple_sdk_flags
        if apple_flags:
            for var in ("CFLAGS", "CXXFLAGS", "LDFLAGS"):
                env.append(var, apple_flags)

        macho_to_amd64 = (self._recipe.settings.arch if cross_building(self._recipe) and self._recipe.settings.os == "Mac" else None)

        content = jinja2.Template(self._premake_file_template, trim_blocks=True, lstrip_blocks=True).render(
            # Pass posix path for better cross-platform compatibility in Lua
            build_folder=Path(self._recipe.folders.build).as_posix(),
            has_recipe_deps=premake_recipe_deps.exists(),
            cppstd=cppstd,
            cstd=self._recipe.settings.compiler_c_standard,
            shared=self._recipe.options.get_safe("shared"),
            pic=self._recipe.options.get_safe("pic"),
            target_build_os=self._target_build_os(),
            macho_to_amd64=macho_to_amd64,
            projects=self._projects,
            flags=_generate_flags(self, self._recipe),
            indent_level=8, )
        save(
            cast(RecipeBase, self), os.path.join(self._recipe.folders.generators, self.filename), content, )
        build_env.generate()

    def _target_build_os(self):
        recipe_os = str(self._recipe.settings.os)
        if recipe_os == "Mac":
            return "macosx"
        return recipe_os.lower()
