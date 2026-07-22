from __future__ import annotations

import copy
import os
import types
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any, Literal, TypeAlias, cast, get_args, get_origin, get_type_hints

PathValue: TypeAlias = str | os.PathLike[str]
CompilerExecutable: TypeAlias = Literal["c", "cpp", "cuda", "objc", "objcxx", "objcpp", "rc", "fortran", "asm", "hip", "ispc"]
InstallStrip: TypeAlias = bool | list[Literal["cmake", "meson", "autotools"]]


@dataclass(slots=True)
class _CoreDownload:
    download_cache: PathValue | None = None


@dataclass(slots=True)
class _CoreNetHttp:
    cacert_path: PathValue | None = None
    clean_system_proxy: bool | None = None
    client_cert: PathValue | tuple[PathValue, PathValue] | None = None
    max_retries: int | None = None
    no_proxy_match: list[str] = field(default_factory=lambda: [])
    proxies: dict[str, str] | None = None
    timeout: int | float | None = None


@dataclass(slots=True)
class _CoreNet:
    http: _CoreNetHttp = field(default_factory=_CoreNetHttp)


@dataclass(slots=True)
class _CoreSources:
    download_cache: PathValue | None = None
    download_urls: list[str] = field(default_factory=lambda: [])


@dataclass(slots=True)
class _Core:
    download: _CoreDownload = field(default_factory=_CoreDownload)
    net: _CoreNet = field(default_factory=_CoreNet)
    sources: _CoreSources = field(default_factory=_CoreSources)


@dataclass(slots=True)
class _AndroidTools:
    cmake_legacy_toolchain: bool | None = None
    ndk_path: PathValue | None = None


@dataclass(slots=True)
class _AppleTools:
    enable_arc: bool | None = None
    enable_bitcode: bool | None = None
    enable_visibility: bool | None = None
    sdk_path: PathValue | None = None


@dataclass(slots=True)
class _CrossBuildingTools:
    can_run: bool | None = None
    cross_build: bool | None = None


@dataclass(slots=True)
class _BuildTools:
    add_rpath_link: bool | None = None
    cflags: list[str] = field(default_factory=lambda: [])
    compiler_executables: dict[CompilerExecutable, PathValue] = field(default_factory=lambda: {})
    compiler_executables_build: dict[CompilerExecutable, PathValue] = field(default_factory=lambda: {})
    cross_building: _CrossBuildingTools = field(default_factory=_CrossBuildingTools)
    cxxflags: list[str] = field(default_factory=lambda: [])
    defines: list[str] = field(default_factory=lambda: [])
    exelinkflags: list[str] = field(default_factory=lambda: [])
    install_strip: InstallStrip | None = None
    jobs: int | None = None
    linker_scripts: list[PathValue] = field(default_factory=lambda: [])
    rcflags: list[str] = field(default_factory=lambda: [])
    sharedlinkflags: list[str] = field(default_factory=lambda: [])
    skip_test: bool | None = None
    sysroot: PathValue | None = None
    verbose: bool = False


@dataclass(slots=True)
class _CMakeToolchainTools:
    enabled_blocks: list[str] = field(default_factory=lambda: [])
    extra_variables: dict[str, object] = field(default_factory=lambda: {})
    find_package_prefer_config: bool | None = None
    presets_environment: Literal["disabled", ""] | None = None
    system_name: str | None = None
    system_processor: str | None = None
    system_version: str | None = None
    toolchain_file: PathValue | None = None
    toolset_arch: str | None = None
    toolset_cuda: PathValue | str | None = None
    user_presets: str | None = None
    user_toolchain: list[PathValue] = field(default_factory=lambda: [])


@dataclass(slots=True)
class _CMakeTools:
    cmake_program: PathValue | None = None
    configure_args: list[str] = field(default_factory=lambda: [])
    ctest_args: list[str] = field(default_factory=lambda: [])
    toolchain: _CMakeToolchainTools = field(default_factory=_CMakeToolchainTools)


@dataclass(slots=True)
class _CompilationTools:
    verbose: bool = False


@dataclass(slots=True)
class _VirtualEnvTools:
    powershell: str | None = None


@dataclass(slots=True)
class _EnvTools:
    deactivation_mode: Literal["function"] | str | None = None
    dotenv: bool | None = None
    virtualenv: _VirtualEnvTools = field(default_factory=_VirtualEnvTools)


@dataclass(slots=True)
class _FileDownloadTools:
    retry: int | None = None
    retry_wait: int | None = None
    verify: bool | None = None


@dataclass(slots=True)
class _FilesTools:
    download: _FileDownloadTools = field(default_factory=_FileDownloadTools)
    unzip_filter: Literal["fully_trusted", "tar", "data"] | str | None = None


@dataclass(slots=True)
class _GnuTools:
    build_triplet: str | None = None
    define_libcxx11_abi: bool | None = None
    disable_flags: list[str] = field(default_factory=lambda: [])
    extra_configure_args: list[str] = field(default_factory=lambda: [])
    host_triplet: str | None = None
    make_program: PathValue | None = None
    pkg_config: PathValue | None = None


@dataclass(slots=True)
class _GnuConfigTools:
    config_guess: PathValue | None = None
    config_sub: PathValue | None = None


@dataclass(slots=True)
class _MesonToolchainTools:
    extra_machine_files: list[PathValue] = field(default_factory=lambda: [])


@dataclass(slots=True)
class _MesonTools:
    toolchain: _MesonToolchainTools = field(default_factory=_MesonToolchainTools)


@dataclass(slots=True)
class _MicrosoftBashTools:
    active: bool | None = None
    path: PathValue | None = None


@dataclass(slots=True)
class _MicrosoftTools:
    bash: _MicrosoftBashTools = field(default_factory=_MicrosoftBashTools)
    msvc_update: str | None = None
    winsdk_version: str | None = None


@dataclass(slots=True)
class _MSBuildTools:
    installation_path: PathValue | None = None
    max_cpu_count: int | None = None
    vs_version: str | None = None


@dataclass(slots=True)
class _MSBuildDepsTools:
    exclude_code_analysis: list[str] = field(default_factory=lambda: [])


@dataclass(slots=True)
class _MSBuildToolchainTools:
    compile_options: dict[str, object] = field(default_factory=lambda: {})


@dataclass(slots=True)
class _AutomakeTools:
    compile_wrapper: PathValue | None = None
    lib_wrapper: PathValue | None = None


@dataclass(slots=True)
class _CPythonTools:
    module_requires_pythonhome: bool | None = None
    python: PathValue | None = None
    python_root: PathValue | None = None
    pythonhome: PathValue | None = None


@dataclass(slots=True)
class _CurlCertTools:
    sha256: str | None = None
    url: str | None = None


@dataclass(slots=True)
class _CurlTools:
    cert: _CurlCertTools = field(default_factory=_CurlCertTools)


@dataclass(slots=True)
class _FreetypeTools:
    libtool_version: str | None = None


@dataclass(slots=True)
class _NcursesTools:
    lib_suffix: str | None = None


@dataclass(slots=True)
class _OpenJDKTools:
    java: PathValue | None = None
    java_home: PathValue | None = None


@dataclass(slots=True)
class _PySideTools:
    root: PathValue | None = None


@dataclass(slots=True)
class _ShibokenTools:
    generator: PathValue | None = None
    generator_root: PathValue | None = None


@dataclass(slots=True)
class _QtTools:
    tools_directory: PathValue | None = None


@dataclass(slots=True)
class _RustTools:
    dir: PathValue | None = None


@dataclass(slots=True)
class _LLVMTools:
    dir: PathValue | None = None


@dataclass(slots=True)
class _StrawberryPerlTools:
    perl: PathValue | None = None


@dataclass(slots=True)
class _Tools:
    android: _AndroidTools = field(default_factory=_AndroidTools)
    apple: _AppleTools = field(default_factory=_AppleTools)
    automake: _AutomakeTools = field(default_factory=_AutomakeTools)
    build: _BuildTools = field(default_factory=_BuildTools)
    cmake: _CMakeTools = field(default_factory=_CMakeTools)
    compilation: _CompilationTools = field(default_factory=_CompilationTools)
    cpython: _CPythonTools = field(default_factory=_CPythonTools)
    curl: _CurlTools = field(default_factory=_CurlTools)
    env: _EnvTools = field(default_factory=_EnvTools)
    files: _FilesTools = field(default_factory=_FilesTools)
    freetype: _FreetypeTools = field(default_factory=_FreetypeTools)
    gnu: _GnuTools = field(default_factory=_GnuTools)
    gnu_config: _GnuConfigTools = field(default_factory=_GnuConfigTools)
    llvm: _LLVMTools = field(default_factory=_LLVMTools)
    meson: _MesonTools = field(default_factory=_MesonTools)
    microsoft: _MicrosoftTools = field(default_factory=_MicrosoftTools)
    msbuild: _MSBuildTools = field(default_factory=_MSBuildTools)
    msbuilddeps: _MSBuildDepsTools = field(default_factory=_MSBuildDepsTools)
    msbuildtoolchain: _MSBuildToolchainTools = field(default_factory=_MSBuildToolchainTools)
    ncurses: _NcursesTools = field(default_factory=_NcursesTools)
    openjdk: _OpenJDKTools = field(default_factory=_OpenJDKTools)
    pyside: _PySideTools = field(default_factory=_PySideTools)
    qt: _QtTools = field(default_factory=_QtTools)
    rust: _RustTools = field(default_factory=_RustTools)
    shiboken: _ShibokenTools = field(default_factory=_ShibokenTools)
    strawberryperl: _StrawberryPerlTools = field(default_factory=_StrawberryPerlTools)


@dataclass(slots=True)
class Conf:
    core: _Core = field(default_factory=_Core)
    tools: _Tools = field(default_factory=_Tools)

    def __bool__(self) -> bool:
        return self != Conf()

    def copy(self) -> Conf:
        return copy.deepcopy(self)

    def compose_conf(self, other: Conf) -> Conf:
        _compose_dataclass(self, other)
        return self

    def serialize_state(self) -> dict[str, object]:
        return _to_jsonable(asdict(self))

    def deserialize_state(self, content: dict[str, object]) -> Conf:
        _load_dataclass(self, content)
        return self


def _compose_dataclass(current: Any, other: Any):
    for data_field in fields(current):
        name = data_field.name
        current_value = getattr(current, name)
        other_value = getattr(other, name)
        if is_dataclass(current_value):
            _compose_dataclass(current_value, other_value)
        elif isinstance(current_value, dict) and isinstance(other_value, dict):
            merged: dict[Any, Any] = copy.deepcopy(cast("dict[Any, Any]", other_value))
            merged.update(cast("dict[Any, Any]", current_value))
            setattr(current, name, merged)
        elif isinstance(current_value, list) and isinstance(other_value, list):
            if not current_value and other_value:
                setattr(current, name, copy.deepcopy(cast("list[Any]", other_value)))
        elif current_value is None and other_value is not None:
            setattr(current, name, copy.deepcopy(other_value))


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(cast("Any", value)))
    if isinstance(value, dict):
        return {key: _to_jsonable(val) for key, val in cast("dict[Any, Any]", value).items()}
    if isinstance(value, list):
        return [_to_jsonable(val) for val in cast("list[Any]", value)]
    if isinstance(value, tuple):
        return [_to_jsonable(val) for val in cast("tuple[Any, ...]", value)]
    if hasattr(value, "__fspath__"):
        return os.fspath(cast("os.PathLike[str]", value))
    return value


def _load_dataclass(target: object, content: dict[str, object]):
    type_hints = get_type_hints(type(target))
    for data_field in fields(cast("Any", target)):
        if data_field.name not in content:
            continue
        value = content[data_field.name]
        current_value = getattr(target, data_field.name)
        if is_dataclass(current_value) and isinstance(value, dict):
            _load_dataclass(current_value, cast("dict[str, object]", value))
        else:
            setattr(target, data_field.name, _restore_value(value, type_hints[data_field.name]))


def _restore_value(value: Any, annotation: Any) -> Any:
    if value is None:
        return None
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is list:
        item_type = args[0] if args else object
        return [_restore_value(item, item_type) for item in value]
    if origin is dict:
        return dict(value)
    if origin is tuple:
        return tuple(value)
    if origin is Literal:
        return value
    if origin is type(None):
        return value
    if origin in (types.UnionType,):
        tuple_args = [arg for arg in args if get_origin(arg) is tuple]
        if tuple_args and isinstance(value, list):
            return _restore_value(value, tuple_args[0])
    if origin is not None and type(None) in args:
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            return _restore_value(value, non_none_args[0])
    return value
