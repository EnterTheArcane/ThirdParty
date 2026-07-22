import jinja2
import os
import textwrap
from typing import Any
from xml.dom import minidom

from thirdparty._internal.util.detect_vs import vs_installation_path
from thirdparty._internal.model.settings import Settings
from thirdparty._internal.util.files import save, load
from thirdparty.build import build_jobs
from thirdparty.errors import RecipeException
from thirdparty.microsoft.visual import VCVars, msvs_toolset, msvc_runtime_flag, msvc_platform_from_arch, vs_ide_version
from thirdparty.recipe import RecipeBase


class MSBuildToolchain:
    """
    MSBuildToolchain class generator
    """

    filename = "recipe_toolchain.props"

    _config_toolchain_props = textwrap.dedent(
        """\
        <?xml version="1.0" encoding="utf-8"?>
        <Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
            {% if toolset_version_full_path %}
            <Import Project="{{toolset_version_full_path}}" />
            {% endif %}
            <ItemDefinitionGroup>
            <ClCompile>
                <PreprocessorDefinitions>{{ defines }}%(PreprocessorDefinitions)</PreprocessorDefinitions>
                <AdditionalOptions>{{ compiler_flags }} %(AdditionalOptions)</AdditionalOptions>
                <RuntimeLibrary>{{ runtime_library }}</RuntimeLibrary>
                {% if cstd %}<LanguageStandard_C>{{ cstd }}</LanguageStandard_C>{% endif %}
                <LanguageStandard>{{ cppstd }}</LanguageStandard>{{ parallel }}{{ compile_options }}
            </ClCompile>
            <Link>
                <AdditionalOptions>{{ linker_flags }} %(AdditionalOptions)</AdditionalOptions>
            </Link>
            <ResourceCompile>
                <PreprocessorDefinitions>{{ defines }}%(PreprocessorDefinitions)</PreprocessorDefinitions>
                {% if rc_flags %}<AdditionalOptions>{{ rc_flags }} %(AdditionalOptions)</AdditionalOptions>{% endif %}
            </ResourceCompile>
            </ItemDefinitionGroup>
            <PropertyGroup Label="Configuration">
            {% if winsdk_version %}
            <WindowsTargetPlatformVersion>{{ winsdk_version}}</WindowsTargetPlatformVersion>
            {% endif %}
            <PlatformToolset>{{ toolset }}</PlatformToolset>
            {% for k, v in properties.items() %}
            <{{k}}>{{ v }}</{{k}}>
            {% endfor %}
            </PropertyGroup>
        </Project>
        """)

    def __init__(self, recipe: RecipeBase):
        """
        :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
        """
        self._recipe = recipe
        #: Dict-like that defines the preprocessor definitions
        self.preprocessor_definitions: dict[str, str | None] = {}
        #: Dict with compile options that will be added as <key>value</key> in the ClCompile section
        self.compile_options: dict[str, Any] = {}
        #: List of all the CXX flags
        self.cxxflags: list[str] = []
        #: List of all the C flags
        self.cflags: list[str] = []
        #: List of all the LD linker flags
        self.ldflags: list[str] = []
        #: List of all the RC (resource compiler) flags
        self.rcflags: list[str] = []
        #: The build type. By default, the ``recipe.settings.build_type`` value
        self.configuration = recipe.settings.build_type
        #: The runtime flag. By default, it'll be based on the `compiler.runtime` setting.
        self.runtime_library = self._runtime_library()
        #: cppstd value. By default, ``compiler.cppstd`` one.
        self.cppstd = recipe.settings.compiler_cxx_standard
        self.cstd = recipe.settings.compiler_c_standard
        #: VS IDE Toolset, e.g., ``"v140"``. If ``compiler=msvc``, you can use ``compiler.toolset``
        #: setting, else, it'll be based on ``msvc`` version.
        self.toolset = msvs_toolset(recipe)
        self.properties: dict[str, Any] = {}
        self.toolset_version_full_path = _get_toolset_props(recipe)

    def _name_condition(self, settings: Settings):
        platform = msvc_platform_from_arch(settings.arch)
        props = [
            ("Configuration", self.configuration), ("Platform", platform),
        ]

        name = "".join("_%s" % v for _, v in props if v is not None)  # pyright: ignore[reportUnnecessaryComparison]  # defensive: prune unset props
        condition = " And ".join("'$(%s)' == '%s'" % (k, v) for k, v in props if v is not None)  # pyright: ignore[reportUnnecessaryComparison]  # defensive: prune unset props
        return name.lower(), condition

    def generate(self):
        """
        Generates a ``recipe_toolchain.props``, a ``recipe_toolchain_<config>.props``, and,
        if ``compiler=msvc``, a ``vcvars_env.bat`` files. In the first two cases, they'll have the
        valid XML format with all the good settings like any other VS project ``*.props`` file. The
        last one emulates the ``vcvarsall.bat`` env script. See also :class:`VCVars`.
        """
        name, condition = self._name_condition(self._recipe.settings)
        config_filename = f"recipe_toolchain{name}.props"
        # Writing the props files
        self._write_config_toolchain(config_filename)
        self._write_main_toolchain(config_filename, condition)
        VCVars(self._recipe).generate()

    def _runtime_library(self):
        return {
            "MT": "MultiThreaded", "MTd": "MultiThreadedDebug", "MD": "MultiThreadedDLL", "MDd": "MultiThreadedDebugDLL",
        }.get(msvc_runtime_flag(self._recipe), "")

    @property
    def context_config_toolchain(self):
        def format_macro(key: str, value: str | None) -> str:
            return "%s=%s" % (key, value) if value is not None else key

        cxxflags, cflags, defines, sharedlinkflags, exelinkflags, rcflags = self._get_extra_flags()
        preprocessor_definitions = "".join(["%s;" % format_macro(k, v) for k, v in self.preprocessor_definitions.items()])
        defines = preprocessor_definitions + "".join("%s;" % d for d in defines)
        self.cxxflags.extend(cxxflags)
        self.cflags.extend(cflags)
        self.ldflags.extend(sharedlinkflags + exelinkflags)
        self.rcflags.extend(rcflags)

        cppstd = "stdcpp%s" % self.cppstd if self.cppstd else ""
        cstd = f"stdc{self.cstd}" if self.cstd else ""
        runtime_library = self.runtime_library
        toolset = self.toolset or ""
        conf_options = self._recipe.conf.tools.msbuildtoolchain.compile_options
        self.compile_options.update(conf_options)
        parallel = ""
        njobs = build_jobs(self._recipe)
        if njobs:
            parallel = "".join(
                [
                    "\n      <MultiProcessorCompilation>True</MultiProcessorCompilation>", f"\n      <ProcessorNumber>{njobs}</ProcessorNumber>",
                ])
        compile_options = "".join(
            f"\n      <{k}>{v}</{k}>" for k, v in self.compile_options.items())

        winsdk_version = self._recipe.conf.tools.microsoft.winsdk_version
        winsdk_version = winsdk_version or self._recipe.settings.os_version

        return {
            "defines": defines,
            "compiler_flags": " ".join(self.cxxflags + self.cflags),
            "linker_flags": " ".join(self.ldflags),
            "rc_flags": " ".join(self.rcflags),
            "cppstd": cppstd,
            "cstd": cstd,
            "runtime_library": runtime_library,
            "toolset": toolset,
            "compile_options": compile_options,
            "parallel": parallel,
            "properties": self.properties,
            "winsdk_version": winsdk_version,
            "toolset_version_full_path": self.toolset_version_full_path,
        }

    def _write_config_toolchain(self, config_filename: str):
        config_filepath = os.path.join(self._recipe.folders.generators, config_filename)
        config_props = jinja2.Template(
            self._config_toolchain_props, trim_blocks=True, lstrip_blocks=True).render(**self.context_config_toolchain)
        self._recipe.output.info("MSBuildToolchain created %s" % config_filename)
        save(config_filepath, config_props)

    def _write_main_toolchain(self, config_filename: str, condition: str):
        main_toolchain_path = os.path.join(self._recipe.folders.generators, self.filename)
        if os.path.isfile(main_toolchain_path):
            content = load(main_toolchain_path)
        else:
            content = textwrap.dedent(
                """\
                <?xml version="1.0" encoding="utf-8"?>
                <Project ToolsVersion="4.0"
                        xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
                    <ImportGroup Label="PropertySheets" >
                    </ImportGroup>
                    <PropertyGroup Label="RecipePackageInfo">
                        <RecipePackageName>{}</RecipePackageName>
                        <RecipePackageVersion>{}</RecipePackageVersion>
                    </PropertyGroup>
                </Project>
                """)

            recipe_package_name = self._recipe.name if self._recipe.name else ""
            recipe_package_version = self._recipe.version if self._recipe.version else ""
            content = content.format(recipe_package_name, recipe_package_version)

        dom = minidom.parseString(content)
        try:
            import_group = dom.getElementsByTagName("ImportGroup")[0]
        except Exception:
            raise RecipeException(f"Broken {self.filename}. Remove the file and try again")
        children = import_group.getElementsByTagName("Import")
        for node in children:
            if (config_filename == node.getAttribute("Project") and condition == node.getAttribute("Condition")):
                break  # the import statement already exists
        else:  # create a new import statement
            import_node = dom.createElement("Import")
            import_node.setAttribute("Condition", condition)
            import_node.setAttribute("Project", config_filename)
            import_group.appendChild(import_node)

        recipe_toolchain = dom.toprettyxml()
        recipe_toolchain = "\n".join(line for line in recipe_toolchain.splitlines() if line.strip())
        self._recipe.output.info(f"MSBuildToolchain writing {self.filename}")
        save(main_toolchain_path, recipe_toolchain)

    def _get_extra_flags(self):
        # Now, it's time to get all the flags defined by the user
        cxxflags = self._recipe.conf.tools.build.cxxflags
        cflags = self._recipe.conf.tools.build.cflags
        sharedlinkflags = self._recipe.conf.tools.build.sharedlinkflags
        exelinkflags = self._recipe.conf.tools.build.exelinkflags
        rcflags = self._recipe.conf.tools.build.rcflags
        defines = self._recipe.conf.tools.build.defines
        return cxxflags, cflags, defines, sharedlinkflags, exelinkflags, rcflags


def _get_toolset_props(recipe: RecipeBase):
    msvc_update = recipe.conf.tools.microsoft.msvc_update
    compiler_update = msvc_update or recipe.settings.compiler_update
    if compiler_update is None:
        return

    vs_version = vs_ide_version(recipe)
    if int(vs_version) <= 14:
        return
    vs_install_path = recipe.conf.tools.msbuild.installation_path
    vs_path = vs_install_path or vs_installation_path(vs_version)
    if not vs_path or not os.path.isdir(vs_path):
        return

    basebuild = os.path.normpath(os.path.join(vs_path, "VC/Auxiliary/Build"))
    # The equivalent of compiler 19.26 is toolset 14.26
    compiler_version = str(recipe.settings.compiler_version)
    vcvars_ver = f"14.{compiler_version[-1]}{compiler_update}"
    for folder in os.listdir(basebuild):
        if not os.path.isdir(os.path.join(basebuild, folder)):
            continue
        if folder.startswith(vcvars_ver):
            result = folder
            return os.path.join(basebuild, result, f"Microsoft.VCToolsVersion.{result}.props")
