import os

from thirdparty.build import build_jobs
from thirdparty.meson.toolchain import MesonToolchain
from thirdparty.recipe import RecipeBase
from thirdparty.shell import run


class Meson:
    """
    This class calls Meson commands when a package is being built. Notice that
    this one should be used together with the ``MesonToolchain`` generator.
    """

    _recipe: RecipeBase

    def __init__(self, recipe: RecipeBase):
        """
        :param recipe: ``< RecipeBase object >`` The current recipe object. Always use ``self``.
        """
        self._recipe = recipe

    def configure(self):
        """
        Runs ``meson setup [FILE] "BUILD_FOLDER" "SOURCE_FOLDER" [-Dprefix=/]``
        command, where ``FILE`` could be ``--native-file recipe_meson_native.ini``
        (if native builds) or ``--cross-file recipe_meson_cross.ini`` (if cross builds).
        """
        source_folder = self._recipe.folders.source
        build_folder = self._recipe.folders.build
        generators_folder = self._recipe.folders.generators
        cross = os.path.join(generators_folder, MesonToolchain.cross_filename)
        native = os.path.join(generators_folder, MesonToolchain.native_filename)
        is_cross_build = os.path.exists(cross)
        machine_files = list(self._recipe.conf.tools.meson.toolchain.extra_machine_files)
        cmd = "meson setup "
        if is_cross_build:
            machine_files.insert(0, cross)
            cmd += " ".join([f'--cross-file "{file}"' for file in machine_files])
        if os.path.exists(native):
            if not is_cross_build:  # machine files are only appended to the cross or the native one
                machine_files.insert(0, native)
                cmd += " ".join([f'--native-file "{file}"' for file in machine_files])
            else:  # extra native file for cross-building scenarios
                cmd += f' --native-file "{native}"'
        cmd += f' "{build_folder}" "{source_folder}"'
        cmd += f" --prefix={self._prefix}"
        self._recipe.output.info(f"Meson configure cmd: {cmd}")
        run(self._recipe, cmd)

    def build(self, target: str | None = None):
        """
        Runs ``meson compile -C . -j[N_JOBS] [TARGET]`` in the build folder.
        You can specify ``N_JOBS`` through the configuration line ``tools.build:jobs=N_JOBS``
        in your profile ``[conf]`` section.

        :param target: ``str`` Specifies the target to be executed.
        """
        meson_build_folder = self._recipe.folders.build
        cmd = f'meson compile -C "{meson_build_folder}"'
        njobs = build_jobs(self._recipe)
        if njobs:
            cmd += f" -j{njobs}"
        if target:
            cmd += f" {target}"
        verbosity = self._build_verbosity
        if verbosity:
            cmd += " " + verbosity
        self._recipe.output.info(f"Meson build cmd: {cmd}")
        run(self._recipe, cmd)

    def install(self, cli_args: list[str] | None = None):
        """
        Runs ``meson install -C "." --destdir ..`` in the build folder.

        :param cli_args: List of arguments to be added to the command:
                    ``meson install -C "." --destdir ... arg1 arg2``
        """
        meson_build_folder = self._recipe.folders.build.as_posix()
        meson_package_folder = self._recipe.folders.package.as_posix()
        # Assuming meson >= 0.57.0
        cmd = f'meson install -C "{meson_build_folder}" --destdir "{meson_package_folder}"'
        verbosity = self._install_verbosity
        if verbosity:
            cmd += " " + verbosity
        install_strip = self._recipe.conf.tools.build.install_strip
        do_strip = install_strip if isinstance(install_strip, bool) else "meson" in (install_strip or [])
        if do_strip:
            cmd += " --strip"
        if cli_args:
            cmd += " " + " ".join(cli_args)
        run(self._recipe, cmd)
        self._fix_msvc_static_lib_names()

    def _fix_msvc_static_lib_names(self):
        """Rename meson's GNU-style static libraries to the MSVC convention.

        Meson always emits static libraries as ``libNAME.a`` (and import libraries as
        ``libNAME.dll.a``), even under MSVC where the archive is a valid COFF ``lib.exe``
        output. MSVC consumers link ``-lNAME`` which resolves to ``NAME.lib``, so rename
        ``lib<name>.a`` -> ``<name>.lib`` in each libdir. No-op for non-MSVC toolchains,
        where ``lib<name>.a`` is already the correct native name.
        """
        from thirdparty.files import rename

        if not self._recipe.settings.compiler_runtime:
            return
        for libdir in self._recipe.info.libdirs:
            full_folder = self._recipe.folders.package / libdir
            for ext in [".dll.a", ".dll.lib", ".a"]:
                for filepath in full_folder.glob(f"*{ext}"):
                    libname = filepath.name[0:-len(ext)]
                    if libname[0:3] == "lib":
                        libname = libname[3:]
                    dst = filepath.parent / f"{libname}.lib"
                    if dst.exists():
                        dst.unlink()
                    rename(self._recipe, filepath, dst)

    def test(self):
        """
        Runs ``meson test -v -C "."`` in the build folder.
        """
        if self._recipe.conf.tools.build.skip_test:
            return
        meson_build_folder = self._recipe.folders.build
        cmd = f'meson test -v -C "{meson_build_folder}"'
        # TODO: Do we need vcvars for test?
        # TODO: This should use runenvenv, but what if meson itself is a build-require?
        run(self._recipe, cmd)

    @property
    def _build_verbosity(self) -> str:
        # verbosity of build tools. This passes -v to ninja, for example.
        # See https://github.com/mesonbuild/meson/blob/master/mesonbuild/mcompile.py#L156
        return "--verbose" if self._recipe.conf.tools.compilation.verbose else ""

    @property
    def _install_verbosity(self) -> str:
        # https://github.com/mesonbuild/meson/blob/master/mesonbuild/minstall.py#L81
        # Errors are always logged, and status about installed files is controlled by this flag,
        # so it's a bit backwards
        return "--quiet" if not self._recipe.conf.tools.build.verbose else ""

    @property
    def _prefix(self) -> str:
        """Generate a valid ``--prefix`` argument value for meson.
        For this recipe system, the prefix must be similar to the Unix root directory ``/``.

        The result of this function should be passed to
        ``meson setup --prefix={self._prefix} ...``

        Python 3.13 changed the semantics of ``/`` on the Windows ntpath module,
        it is now special-cased as a relative directory.
        Thus, ``os.path.isabs("/")`` is true on Linux but false on Windows.
        So for Windows, an equivalent path is ``C:\\``. However, this can be
        parsed wrongly in meson in specific circumstances due to the trailing
        backslash. Hence, we also use forward slashes for Windows, leaving us
        with ``C:/`` or similar paths.

        See also
        --------
        * The meson issue discussing the need to set ``--prefix`` to ``/``:
            `mesonbuild/meson#12880 <https://github.com/mesonbuild/meson/issues/12880>`_
        * The cpython PR introducing the ``/`` behavior change:
            `python/cpython#113829 <https://github.com/python/cpython/pull/113829>`_
        * The issue detailing the erroneous parsing of ``\\``:
            `upstream issue 14213`_
        """
        return os.path.abspath("/").replace("\\", "/")
