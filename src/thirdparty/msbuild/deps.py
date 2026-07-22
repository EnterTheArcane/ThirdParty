import fnmatch
import jinja2
import os
import re
import textwrap
from typing import Any
from xml.dom import minidom

from thirdparty._internal.model.dependencies import get_transitive_requires
from thirdparty._internal.util.files import load, save
from thirdparty._internal.util.generators import relativize_path
from thirdparty.errors import RecipeException
from thirdparty.microsoft.visual import msvc_platform_from_arch
from thirdparty.recipe import RecipeBase

VALID_LIB_EXTENSIONS = (".so", ".lib", ".a", ".dylib", ".bc")


class MSBuildDeps:
    """
    MSBuildDeps class generator
    recipe_deps.props: unconditional import of all *direct* dependencies only
    """

    _vars_props = textwrap.dedent(
        """\
        <?xml version="1.0" encoding="utf-8"?>
        <Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
            <PropertyGroup Label="RecipeVariables">
            <Recipe{{name}}RootFolder>{{root_folder}}</Recipe{{name}}RootFolder>
            <Recipe{{name}}BinaryDirectories>{{bin_dirs}}</Recipe{{name}}BinaryDirectories>
            {% if host_context %}
            <Recipe{{name}}CompilerFlags>{{compiler_flags}}</Recipe{{name}}CompilerFlags>
            <Recipe{{name}}LinkerFlags>{{linker_flags}}</Recipe{{name}}LinkerFlags>
            <Recipe{{name}}PreprocessorDefinitions>{{definitions}}</Recipe{{name}}PreprocessorDefinitions>
            <Recipe{{name}}IncludeDirectories>{{include_dirs}}</Recipe{{name}}IncludeDirectories>
            <Recipe{{name}}ResourceDirectories>{{res_dirs}}</Recipe{{name}}ResourceDirectories>
            <Recipe{{name}}LibraryDirectories>{{lib_dirs}}</Recipe{{name}}LibraryDirectories>
            <Recipe{{name}}Libraries>{{libs}}</Recipe{{name}}Libraries>
            <Recipe{{name}}SystemLibs>{{system_libs}}</Recipe{{name}}SystemLibs>
            {% endif %}
            </PropertyGroup>
        </Project>
        """)

    _conf_props = textwrap.dedent(
        """\
        <?xml version="1.0" encoding="utf-8"?>
        <Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
            <ImportGroup Label="PropertySheets">
            {% for dep in deps %}
            <Import Condition="'$(recipe_{{dep}}_props_imported)' != 'True'" Project="recipe_{{dep}}.props"/>
            {% endfor %}
            </ImportGroup>
            <ImportGroup Label="PropertySheets">
            <Import Project="{{vars_filename}}"/>
            </ImportGroup>
            {% if host_context %}
            <PropertyGroup>
            <RecipeDebugPath>$(Recipe{{name}}BinaryDirectories);$(RecipeDebugPath)</RecipeDebugPath>
            <LocalDebuggerEnvironment>PATH=$(RecipeDebugPath);%PATH%</LocalDebuggerEnvironment>
            <DebuggerFlavor>WindowsLocalDebugger</DebuggerFlavor>
            {% if ca_exclude %}
            <CAExcludePath>$(Recipe{{name}}IncludeDirectories);$(CAExcludePath)</CAExcludePath>
            {% endif %}
            </PropertyGroup>
            <ItemDefinitionGroup>
            <ClCompile>
                <AdditionalIncludeDirectories>$(Recipe{{name}}IncludeDirectories)%(AdditionalIncludeDirectories)</AdditionalIncludeDirectories>
                <PreprocessorDefinitions>$(Recipe{{name}}PreprocessorDefinitions)%(PreprocessorDefinitions)</PreprocessorDefinitions>
                <AdditionalOptions>$(Recipe{{name}}CompilerFlags) %(AdditionalOptions)</AdditionalOptions>
            </ClCompile>
            <Link>
                <AdditionalLibraryDirectories>$(Recipe{{name}}LibraryDirectories)%(AdditionalLibraryDirectories)</AdditionalLibraryDirectories>
                <AdditionalDependencies>$(Recipe{{name}}Libraries)%(AdditionalDependencies)</AdditionalDependencies>
                <AdditionalDependencies>$(Recipe{{name}}SystemLibs)%(AdditionalDependencies)</AdditionalDependencies>
                <AdditionalOptions>$(Recipe{{name}}LinkerFlags) %(AdditionalOptions)</AdditionalOptions>
            </Link>
            <Midl>
                <AdditionalIncludeDirectories>$(Recipe{{name}}IncludeDirectories)%(AdditionalIncludeDirectories)</AdditionalIncludeDirectories>
            </Midl>
            <ResourceCompile>
                <AdditionalIncludeDirectories>$(Recipe{{name}}IncludeDirectories)%(AdditionalIncludeDirectories)</AdditionalIncludeDirectories>
                <PreprocessorDefinitions>$(Recipe{{name}}PreprocessorDefinitions)%(PreprocessorDefinitions)</PreprocessorDefinitions>
            </ResourceCompile>
            </ItemDefinitionGroup>
            {% else %}
            <PropertyGroup>
            <ExecutablePath>$(Recipe{{name}}BinaryDirectories)$(ExecutablePath)</ExecutablePath>
            </PropertyGroup>
            {% endif %}
        </Project>
        """)

    _recipe: RecipeBase
    configuration: str | None
    configuration_key: str
    platform: str
    platform_key: str

    def __init__(self, recipe: RecipeBase):
        """
        :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
        """
        self._recipe = recipe
        #: Defines the build type. By default, the value of ``settings.build_type``.
        self.configuration = recipe.settings.build_type
        #: Defines the configuration key used to conditionally select which property sheet to
        #: import (defaults to ``"Configuration"``).
        self.configuration_key = "Configuration"
        # TODO: This platform is not exactly the same as ``msbuild_arch``, because it differs
        # in x86=>Win32
        #: Platform name, e.g., ``Win32`` if ``settings.arch == "x86"``.
        self.platform = msvc_platform_from_arch(str(recipe.settings.arch))
        #: Defines the platform key used to conditionally select which property sheet to
        #: import (defaults to ``"Platform"``).
        self.platform_key = "Platform"
        #: List of packages names patterns to add Visual Studio ``CAExcludePath`` property
        #: to each match as part of its ``recipe_[DEP]_[CONFIG].props``.
        self.exclude_code_analysis = self._recipe.conf.tools.msbuilddeps.exclude_code_analysis

    def generate(self):
        """
        Generates ``recipe_<pkg>_<config>_vars.props``, ``recipe_<pkg>_<config>.props``,
        and ``recipe_<pkg>.props`` files into the ``recipe.folders.generators``.
        """
        if self.configuration is None:
            raise RecipeException("MSBuildDeps.configuration is None, it should have a value")
        if self.platform is None:  # pyright: ignore[reportUnnecessaryComparison]  # defensive invariant check
            raise RecipeException("MSBuildDeps.platform is None, it should have a value")
        generator_files = self._content()
        for generator_file, content in generator_files.items():
            save(generator_file, content)

    def _config_filename(self) -> str:
        props = [
            self.configuration, self.platform,
        ]
        name = "".join("_%s" % v for v in props)
        return name.lower()

    def _condition(self) -> str:
        props = [
            (self.configuration_key, self.configuration), (self.platform_key, self.platform),
        ]
        condition = " And ".join("'$(%s)' == '%s'" % (k, v) for k, v in props)
        return condition

    @staticmethod
    def _dep_name(dep: Any, build: bool) -> str:
        dep_name = dep.name
        if build:  # dep.context == CONTEXT_BUILD:
            dep_name += "_build"
        return MSBuildDeps._get_valid_xml_format(dep_name)

    @staticmethod
    def _get_valid_xml_format(name: str) -> str:
        return re.compile(r"[.+]").sub("_", name)

    def _vars_props_file(
        self,
        require: Any,
        dep: Any,
        name: str,
        info: Any,
        build: bool) -> str:
        """
        content for recipe_vars_poco_x86_release.props, containing the variables for 1 config
        This will be for 1 package or for one component of a package
        :return: varfile content
        """

        def add_valid_ext(libname: str, libdirs: list[str] | None = None) -> str:
            ext = os.path.splitext(libname)[1]
            if ext in VALID_LIB_EXTENSIONS:
                return f"{libname};"

            lib_name = f"{libname}.lib"
            if libdirs and not any(lib_name in os.listdir(d) for d in libdirs if os.path.isdir(d)):
                meson_name = f"lib{libname}.a"
                if any(meson_name in os.listdir(d) for d in libdirs if os.path.isdir(d)):
                    lib_name = meson_name
            return f"{lib_name};"

        pkg_placeholder = f"$(Recipe{name}RootFolder)"

        def escape_path(path: str) -> str:
            # https://docs.microsoft.com/en-us/visualstudio/msbuild/
            #                          how-to-escape-special-characters-in-msbuild
            # https://docs.microsoft.com/en-us/visualstudio/msbuild/msbuild-special-characters
            return os.fspath(path).lstrip("/")

        def join_paths(paths: list[str]) -> str:
            # TODO: ALmost copied from CMakeDeps TargetDataContext
            ret: list[str] = []
            for p in paths:
                assert os.path.isabs(p), f"{p} is not absolute"
                full_path = escape_path(p)
                if full_path.startswith(root_folder):
                    rel = full_path[len(root_folder) + 1:]
                    full_path = ("%s/%s" % (pkg_placeholder, rel))
                ret.append(full_path)
            return "".join(f"{e};" for e in ret)

        root_folder = (
            dep.folders.package
            if dep.folders.base_package is not None
            else dep.folders.recipe
        )
        root_folder = escape_path(root_folder)
        # Make the root_folder relative to the generated recipe_vars_xxx.props file
        relative_root_folder: str = relativize_path(
            root_folder, self._recipe, "$(MSBuildThisFileDirectory)", normalize=False)

        bin_dirs = join_paths(info.bindirs)
        res_dirs = join_paths(info.resdirs)
        include_dirs = join_paths(info.includedirs)
        lib_dirs = join_paths(info.libdirs)
        libs = "".join([add_valid_ext(lib, info.libdirs) for lib in info.libs])
        # TODO: Missing objects
        system_libs = "".join([add_valid_ext(sys_dep) for sys_dep in info.system_libs])
        definitions = "".join("%s;" % d for d in info.defines)
        compiler_flags = " ".join(info.cxxflags + info.cflags)
        linker_flags = " ".join(info.sharedlinkflags + info.exelinkflags)

        # traits logic
        if require and not require.headers:
            include_dirs = ""
        if require and not require.libs:
            lib_dirs = ""
            libs = ""
        if require and not require.libs and not require.headers:
            definitions = ""
            compiler_flags = ""
            linker_flags = ""
        if require and not require.run:
            bin_dirs = ""

        fields: dict[str, Any] = {
            "name": name, "root_folder": relative_root_folder, "bin_dirs": bin_dirs, "res_dirs": res_dirs, "include_dirs": include_dirs, "lib_dirs": lib_dirs, "libs": libs, # TODO: Missing objects
            "system_libs": system_libs, "definitions": definitions, "compiler_flags": compiler_flags, "linker_flags": linker_flags, "host_context": not build,
        }
        formatted_template = jinja2.Template(
            self._vars_props, trim_blocks=True, lstrip_blocks=True).render(**fields)
        return formatted_template

    def _activate_props_file(
        self,
        dep_name: str,
        vars_filename: str,
        deps: Any,
        build: bool) -> str:
        """
        Actual activation of the VS variables, per configuration
            - recipe_pkgname_x86_release.props / recipe_pkgname_compname_x86_release.props
        :param dep_name: pkgname / pkgname_compname
        :param deps: the name of other things to be included: [dep1, dep2:compA, ...]
        :param build: if it is a build require or not
        """

        # TODO: This must include somehow the user/channel, most likely pattern to exclude/include
        # Probably also the negation pattern, exclude all not @mycompany/*
        ca_exclude = any(fnmatch.fnmatch(dep_name, p) for p in self.exclude_code_analysis or ())
        template = jinja2.Template(self._conf_props, trim_blocks=True, lstrip_blocks=True)
        content_multi = template.render(
            host_context=not build, name=dep_name, ca_exclude=ca_exclude, vars_filename=vars_filename, deps=deps)
        return content_multi

    @staticmethod
    def _dep_props_file(
        dep_name: str,
        filename: str,
        aggregated_filename: str,
        condition: str,
        content: Any = None) -> str:
        """
        The file aggregating all configurations for a given pkg / component
            - recipe_pkgname.props
        """
        # Current directory is the generators_folder
        if content:
            content_multi = content  # Useful for aggregating multiple components in one pass
        elif os.path.isfile(filename):
            content_multi = load(filename)
        else:
            content_multi = textwrap.dedent(
                """\
                <?xml version="1.0" encoding="utf-8"?>
                <Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
                    <ImportGroup Label="PropertySheets">
                    </ImportGroup>
                    <PropertyGroup>
                    <recipe_{{name}}_props_imported>True</recipe_{{name}}_props_imported>
                    </PropertyGroup>
                </Project>
                """)
            content_multi = jinja2.Template(content_multi).render({"name": dep_name})
        # parse the multi_file and add new import statement if needed
        dom = minidom.parseString(content_multi)
        import_vars = dom.getElementsByTagName("ImportGroup")[0]

        # Current vars
        children = import_vars.getElementsByTagName("Import")
        for node in children:
            if aggregated_filename == node.getAttribute("Project") and condition == node.getAttribute("Condition"):
                break
        else:  # create a new import statement
            import_node = dom.createElement("Import")
            import_node.setAttribute("Condition", condition)
            import_node.setAttribute("Project", aggregated_filename)
            import_vars.appendChild(import_node)

        # Import recipe_dedup.props
        if "recipe_dedup.props" not in content_multi:
            dedup_import = dom.createElement("Import")
            dedup_import.setAttribute("Condition", "'$(RecipeDedupPropsImported)' != 'True'")
            dedup_import.setAttribute("Project", "recipe_dedup.props")
            import_vars.appendChild(dedup_import)

        content_multi = dom.toprettyxml()
        content_multi = "\n".join(line for line in content_multi.splitlines() if line.strip())
        return content_multi

    _recipe_dedup_props = textwrap.dedent(
        """\
        <?xml version="1.0" encoding="utf-8"?>
        <Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
            <PropertyGroup>
            <RecipeDedupPropsImported>True</RecipeDedupPropsImported>
            </PropertyGroup>
            <Target Name="RecipeDeduplicatePaths"
                    BeforeTargets="ClCompile;Link;Midl;ResourceCompile"
                    Condition="'$(RecipeDedupTargetDefined)' != 'True'">
            <PropertyGroup>
                <RecipeDedupTargetDefined>True</RecipeDedupTargetDefined>
            </PropertyGroup>
            <ItemGroup>
                <_RecipeIncludePaths Include="%(ClCompile.AdditionalIncludeDirectories)" />
            </ItemGroup>
            <RemoveDuplicates Inputs="@(_RecipeIncludePaths)">
                <Output TaskParameter="Filtered" ItemName="_RecipeUniqueIncludePaths" />
            </RemoveDuplicates>
            <ItemGroup>
                <ClCompile Condition="'@(_RecipeUniqueIncludePaths)' != ''">
                <AdditionalIncludeDirectories>@(_RecipeUniqueIncludePaths)</AdditionalIncludeDirectories>
                </ClCompile>
            </ItemGroup>
            <ItemGroup>
                <_RecipeLibPaths Include="%(Link.AdditionalLibraryDirectories)" />
            </ItemGroup>
            <RemoveDuplicates Inputs="@(_RecipeLibPaths)">
                <Output TaskParameter="Filtered" ItemName="_RecipeUniqueLibPaths" />
            </RemoveDuplicates>
            <ItemGroup>
                <Link Condition="'@(_RecipeUniqueLibPaths)' != ''">
                <AdditionalLibraryDirectories>@(_RecipeUniqueLibPaths)</AdditionalLibraryDirectories>
                </Link>
            </ItemGroup>
            </Target>
        </Project>
        """)

    def _recipe_deps(self) -> dict[str, str]:
        """ this is a .props file including direct declared dependencies
        """
        # Current directory is the generators_folder
        recipe_deps_filename = "recipe_deps.props"
        direct_deps = self._recipe.dependencies.filter({"direct": True})
        pkg_aggregated_content = textwrap.dedent(
            """\
            <?xml version="1.0" encoding="utf-8"?>
            <Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
                <ImportGroup Label="PropertySheets">
                </ImportGroup>
            </Project>
            """)
        for req, dep in direct_deps.items():
            dep_name = self._dep_name(dep, req.build)
            filename = "recipe_%s.props" % dep_name
            comp_condition = "'$(recipe_%s_props_imported)' != 'True'" % dep_name
            pkg_aggregated_content = self._dep_props_file(
                "", recipe_deps_filename, filename, condition=comp_condition, content=pkg_aggregated_content)
        return {recipe_deps_filename: pkg_aggregated_content}

    def _package_props_files(
        self,
        require: Any,
        dep: Any,
        build: bool = False) -> dict[str, str]:
        """ all the files for a given package:
        - recipe_pkgname_vars_config.props: definition of variables, one per config
        - recipe_pkgname_config.props: The one using those variables. This is very different for
                                      Host and build, build only activate <ExecutablePath>
        - recipe_pkgname.props: Conditional aggregate xxx_config.props based on active config
        """
        conf_name = self._config_filename()
        condition = self._condition()
        dep_name = self._dep_name(dep, build)
        result: dict[str, str] = {}
        pkg_deps = get_transitive_requires(self._recipe, dep)  # only non-skipped dependencies
        if dep.info.has_components:
            pkg_aggregated_content = None
            for comp_name, comp_info in dep.info.components.items():
                full_comp_name = f"{dep_name}_{self._get_valid_xml_format(comp_name)}"
                vars_filename = "recipe_%s_vars%s.props" % (full_comp_name, conf_name)
                activate_filename = "recipe_%s%s.props" % (full_comp_name, conf_name)
                comp_filename = "recipe_%s.props" % full_comp_name
                pkg_filename = "recipe_%s.props" % dep_name

                public_deps: list[str] = []  # To store the xml dependencies/file names
                for required_pkg, required_comp in comp_info.parsed_requires():
                    if required_pkg is not None:  # Points to a component of a different package
                        try:
                            required = pkg_deps[required_pkg]
                        except KeyError:  # The transitive dep might have been skipped
                            required = None
                        if required:  # The transitive dep might have been skipped
                            required_name = self._dep_name(required, build)
                            public_deps.append(
                                required_name if required_pkg == required_comp else f"{required_name}_{required_comp}")
                    else:  # Points to a component of same package
                        public_deps.append(f"{dep_name}_{required_comp}")
                public_deps = [self._get_valid_xml_format(d) for d in public_deps]
                result[vars_filename] = self._vars_props_file(
                    require, dep, full_comp_name, comp_info, build=build)
                result[activate_filename] = self._activate_props_file(
                    full_comp_name, vars_filename, public_deps, build=build)
                result[comp_filename] = self._dep_props_file(
                    full_comp_name, comp_filename, activate_filename, condition)
                comp_condition = "'$(recipe_%s_props_imported)' != 'True'" % full_comp_name
                pkg_aggregated_content = self._dep_props_file(
                    dep_name, pkg_filename, comp_filename, condition=comp_condition, content=pkg_aggregated_content)
                result[pkg_filename] = pkg_aggregated_content
        else:
            info = dep.info
            vars_filename = "recipe_%s_vars%s.props" % (dep_name, conf_name)
            activate_filename = "recipe_%s%s.props" % (dep_name, conf_name)
            pkg_filename = "recipe_%s.props" % dep_name
            public_deps = [self._dep_name(d, build) for d in pkg_deps.values()]

            result[vars_filename] = self._vars_props_file(
                require, dep, dep_name, info, build=build)
            result[activate_filename] = self._activate_props_file(
                dep_name, vars_filename, public_deps, build=build)
            result[pkg_filename] = self._dep_props_file(
                dep_name, pkg_filename, activate_filename, condition=condition)
        return result

    def _content(self) -> dict[str, str]:
        if not self._recipe.settings.build_type:
            raise RecipeException("The 'msbuild' generator requires a 'build_type' setting value")
        result: dict[str, str] = {}

        for req, dep in self._recipe.dependencies.host.items():
            result.update(self._package_props_files(req, dep, build=False))
        for req, dep in self._recipe.dependencies.build.items():
            result.update(self._package_props_files(req, dep, build=True))

        # Include all direct tool requirements for host context. This might change
        result.update(self._recipe_deps())

        result["recipe_dedup.props"] = self._recipe_dedup_props

        return result
