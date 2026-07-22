import os
from io import StringIO
from typing import Any, cast

from thirdparty._internal.util.runners import check_output_runner
from thirdparty.build import cmd_args_to_string
from thirdparty.errors import RecipeException
from thirdparty.recipe import RecipeBase
from thirdparty.shell import run


def is_apple_os(recipe: RecipeBase, build_context: bool = False) -> bool:
    """returns True if OS is Apple one (Mac, iOS, tvOS or visionOS)"""
    settings = recipe.settings_build if build_context else recipe.settings
    return str(settings.os) in ["Mac", "iOS", "tvOS", "visionOS"]


def _to_apple_arch(arch: str | None, default: Any = None) -> str | None:
    """converts recipe-style architecture into Apple-style arch"""
    return {
        "X64": "x86_64", "ARM": "arm64",
    }.get(str(arch), default)


def to_apple_arch(recipe: RecipeBase, default: Any = None) -> str | None:
    """converts recipe-style architecture into Apple-style arch"""
    arch_ = recipe.settings.arch
    return _to_apple_arch(arch_, default)


def apple_sdk_path(recipe: RecipeBase, is_cross_building: bool = True) -> str | None:
    sdk_path = recipe.conf.tools.apple.sdk_path
    if not sdk_path:
        # XCRun already knows how to extract os.sdk from recipe.settings
        sdk_path = XCRun(recipe).sdk_path
    if not sdk_path and is_cross_building:
        raise RecipeException(
            "Apple SDK path not found. For cross-compilation, you must "
            "provide a valid SDK path in 'tools.apple:sdk_path' config.")
    return cast("str | None", sdk_path)


def get_apple_sdk_fullname(recipe: RecipeBase) -> str | None:
    """
    Returns the 'os.sdk' + 'os.sdk_version ' value. Every user should specify it because
    there could be several ones depending on the OS architecture.

    Note: In case of MacOS it'll be the same for all the architectures.
    """
    os_ = recipe.settings.os
    os_sdk = recipe.settings.os_sdk
    os_sdk_version = recipe.settings.os_sdk_version or ""
    if os_sdk:
        return f"{os_sdk}{os_sdk_version}"
    elif os_ == "Mac":  # it has only a single value for all the architectures
        return f"macosx{os_sdk_version}"
    elif is_apple_os(recipe):
        raise RecipeException("Please, specify a suitable value for os.sdk.")


def apple_min_version_flag(recipe: RecipeBase) -> str:
    """compiler flag name which controls deployment target"""
    os_ = recipe.settings.os
    os_sdk = recipe.settings.os_sdk
    os_sdk = os_sdk or ("macosx" if os_ == "Mac" else None)
    os_version = recipe.settings.os_version
    if not os_sdk or not os_version:
        # Legacy behavior
        return ""
    if recipe.settings.os_subsystem == "catalyst":
        os_sdk = "iphoneos"
    return {
        "macosx": f"-mmacosx-version-min={os_version}",
        "iphoneos": f"-mios-version-min={os_version}",
        "iphonesimulator": f"-mios-simulator-version-min={os_version}",
        "watchos": f"-mwatchos-version-min={os_version}",
        "watchsimulator": f"-mwatchos-simulator-version-min={os_version}",
        "appletvos": f"-mtvos-version-min={os_version}",
        "appletvsimulator": f"-mtvos-simulator-version-min={os_version}",
        "xros": f"--target=arm64-apple-xros{os_version}",
        "xrsimulator": f"--target=arm64-apple-xros{os_version}-simulator",
    }.get(os_sdk, "")


def resolve_apple_flags(
    recipe: RecipeBase, is_cross_building: bool = False) -> tuple[str, str | None, str | None]:
    """
    Gets the most common flags in Apple systems. If it's a cross-building context
    SDK path is mandatory so if it could raise an exception if SDK is not found.

    :param recipe: <RecipeBase> instance.
    :param is_cross_building: boolean to indicate if it's a cross-building context.
    :return: tuple of Apple flags (apple_min_version_flag, apple_arch_flags, apple_isysroot_flag).
    """
    if not is_apple_os(recipe):
        # Keeping legacy defaults
        return "", None, None

    apple_arch_flags = apple_isysroot_flag = None

    if is_cross_building:
        arch = to_apple_arch(recipe)
        sdk_path = apple_sdk_path(recipe, is_cross_building=is_cross_building)
        apple_isysroot_flag = f"-isysroot {sdk_path}" if sdk_path else ""
        apple_arch_flags = f"-arch {arch}" if arch else ""

    min_version_flag = apple_min_version_flag(recipe)
    return min_version_flag, apple_arch_flags, apple_isysroot_flag


def xcodebuild_deployment_target_key(os_name: str) -> str | None:
    return {
        "Mac": "MACOSX_DEPLOYMENT_TARGET", "iOS": "IPHONEOS_DEPLOYMENT_TARGET", "tvOS": "TVOS_DEPLOYMENT_TARGET", "visionOS": "XROS_DEPLOYMENT_TARGET",
    }.get(os_name) if os_name else None


class XCRun:
    """
    XCRun is a wrapper for the Apple **xcrun** tool used to get information for building.
    """

    def __init__(
        self,
        recipe: RecipeBase,
        sdk: str | None = None):
        """
        :param recipe: Recipefile instance.
        :param sdk: Will skip the flag when ``False`` is passed and will try to adjust the
            sdk it automatically if ``None`` is passed.
        """
        settings = recipe.settings

        if sdk is None and settings:
            sdk = settings.os_sdk

        self._recipe = recipe
        self.settings = settings
        self.sdk = sdk

    def _invoke(self, args: list[str]) -> str:
        command = ["xcrun"]
        if self.sdk:
            command.extend(["-sdk", self.sdk])
        command.extend(args)
        output = StringIO()
        cmd_str = cmd_args_to_string(command)
        run(self._recipe, f"{cmd_str}", stdout=output, quiet=True)
        return output.getvalue().strip()

    def find(self, tool: str) -> str:
        """find SDK tools (e.g. clang, ar, ranlib, lipo, codesign, etc.)"""
        return self._invoke(["--find", tool])

    @property
    def sdk_path(self) -> str:
        """obtain sdk path (aka apple sysroot or -isysroot"""
        return self._invoke(["--show-sdk-path"])

    @property
    def sdk_version(self) -> str:
        """obtain sdk version"""
        return self._invoke(["--show-sdk-version"])

    @property
    def sdk_platform_path(self) -> str:
        """obtain sdk platform path"""
        return self._invoke(["--show-sdk-platform-path"])

    @property
    def sdk_platform_version(self) -> str:
        """obtain sdk platform version"""
        return self._invoke(["--show-sdk-platform-version"])

    @property
    def cc(self) -> str:
        """path to C compiler (CC)"""
        return self.find("clang")

    @property
    def cxx(self) -> str:
        """path to C++ compiler (CXX)"""
        return self.find("clang++")

    @property
    def ar(self) -> str:
        """path to archiver (AR)"""
        return self.find("ar")

    @property
    def ranlib(self) -> str:
        """path to archive indexer (RANLIB)"""
        return self.find("ranlib")

    @property
    def strip(self) -> str:
        """path to symbol removal utility (STRIP)"""
        return self.find("strip")

    @property
    def libtool(self) -> str:
        """path to libtool"""
        return self.find("libtool")

    @property
    def otool(self) -> str:
        """path to otool"""
        return self.find("otool")

    @property
    def install_name_tool(self) -> str:
        """path to install_name_tool"""
        return self.find("install_name_tool")


def _get_dylib_install_name(otool: str, path_to_dylib: str) -> str:
    command = f"{otool} -D {path_to_dylib}"
    output = iter(check_output_runner(command).splitlines())
    # Note: if otool return multiple entries for different architectures
    # assume they are the same and pick the first one.
    for line in output:
        if ":" in line:
            return next(output)
    raise RecipeException(f"Unable to extract install_name for {path_to_dylib}")


def fix_apple_shared_install_name(recipe: RecipeBase):
    """
    Search for all the *dylib* files in the recipe's *package_folder* and fix
    both the ``LC_ID_DYLIB`` and ``LC_LOAD_DYLIB`` fields on those files using the
    *install_name_tool* utility available in macOS to set ``@rpath``.
    """

    if not is_apple_os(recipe):
        return

    xcrun = XCRun(recipe)
    otool = xcrun.otool
    install_name_tool = xcrun.install_name_tool

    def _darwin_is_binary(file: str, binary_type: str) -> bool:
        if binary_type not in ("DYLIB", "EXECUTE") or os.path.islink(file) or os.path.isdir(file):
            return False
        check_file = f"{otool} -hv {file}"
        return binary_type in check_output_runner(check_file)

    def _darwin_collect_binaries(folder: str, binary_type: str) -> list[str]:
        return [os.path.join(folder, f) for f in os.listdir(folder) if _darwin_is_binary(os.path.join(folder, f), binary_type)]

    def _fix_install_name(dylib_path: str, new_name: str):
        command = f"{install_name_tool} {dylib_path} -id {new_name}"
        run(recipe, command)

    def _fix_dep_name(dylib_path: str, old_name: str, new_name: str):
        command = f"{install_name_tool} {dylib_path} -change {old_name} {new_name}"
        run(recipe, command)

    def _get_rpath_entries(binary_file: str) -> list[str]:
        entries: list[str] = []
        command = f"{otool} -l {binary_file}"
        otool_output = check_output_runner(command).splitlines()
        for count, text in enumerate(otool_output):
            pass
            if "LC_RPATH" in text:
                rpath_entry = otool_output[count + 2].split("path ")[1].split(" ")[0]
                entries.append(rpath_entry)
        return entries

    def _get_shared_dependencies(binary_file: str) -> list[str]:
        command = f"{otool} -L {binary_file}"
        all_shared = check_output_runner(command).strip().split(":")[1].strip()
        ret = [s.split("(")[0].strip() for s in all_shared.splitlines()]
        return ret

    def _fix_dylib_files() -> dict[str, str]:
        substitutions: dict[str, str] = {}
        libdirs = getattr(recipe.info, "libdirs")
        for libdir in libdirs:
            full_folder = os.path.join(recipe.folders.package, libdir)
            if not os.path.exists(full_folder):
                raise RecipeException(
                    f"Trying to locate shared libraries, but `{libdir}` "
                    f" not found inside package folder {recipe.folders.package}")
            shared_libs = _darwin_collect_binaries(full_folder, "DYLIB")
            # fix LC_ID_DYLIB in first pass
            for shared_lib in shared_libs:
                install_name = _get_dylib_install_name(otool, shared_lib)
                # TODO: we probably only want to fix the install the name if
                # it starts with `/`.
                rpath_name = f"@rpath/{os.path.basename(install_name)}"
                _fix_install_name(shared_lib, rpath_name)
                substitutions[install_name] = rpath_name

            # fix dependencies in second pass
            for shared_lib in shared_libs:
                for old, new in substitutions.items():
                    _fix_dep_name(shared_lib, old, new)

        return substitutions

    def _fix_executables(substitutions: dict[str, str]):
        # Fix the install name for executables inside the package
        # that reference libraries we just patched
        bindirs = getattr(recipe.info, "bindirs")
        for bindir in bindirs:
            full_folder = os.path.join(recipe.folders.package, bindir)
            if not os.path.exists(full_folder):
                # Skip if the folder does not exist inside the package
                # (e.g. package does not contain executables but bindirs is defined)
                continue
            executables = _darwin_collect_binaries(full_folder, "EXECUTE")
            for executable in executables:

                # Fix install names of libraries from within the same package
                deps = _get_shared_dependencies(executable)
                for dep in deps:
                    dep_base = os.path.join(
                        os.path.dirname(dep), os.path.basename(dep).split(".")[0])
                    match = [k for k in substitutions.keys() if k.startswith(dep_base)]
                    if match:
                        _fix_dep_name(executable, dep, substitutions[match[0]])

                # Add relative rpath to library directories, avoiding possible
                # existing duplicates
                libdirs = getattr(recipe.info, "libdirs")
                libdirs = [os.path.join(recipe.folders.package, libdir) for libdir in libdirs]
                rel_paths = [f"@executable_path/{os.path.relpath(libdir, full_folder)}" for libdir in libdirs]
                existing_rpaths = _get_rpath_entries(executable)
                rpaths_to_add = list(set(rel_paths) - set(existing_rpaths))
                for entry in rpaths_to_add:
                    command = f"{install_name_tool} {executable} -add_rpath {entry}"
                    run(recipe, command)

    substitutes = _fix_dylib_files()

    # Only "fix" executables if dylib files were patched, otherwise
    # there is nothing to do.
    if substitutes:
        _fix_executables(substitutes)


def apple_extra_flags(recipe: RecipeBase) -> list[str]:
    if not is_apple_os(recipe):
        return []
    enable_bitcode = recipe.conf.tools.apple.enable_bitcode
    enable_visibility = recipe.conf.tools.apple.enable_visibility
    is_debug = recipe.settings.build_type == "Debug"
    flags: list[str] = []
    if enable_bitcode:
        if is_debug:
            flags.append("-fembed-bitcode-marker")
        else:
            flags.append("-fembed-bitcode")
    if enable_visibility:
        flags.append("-fvisibility=default")
    if enable_visibility is False:
        flags.extend(["-fvisibility=hidden", "-fvisibility-inlines-hidden"])
    return flags
