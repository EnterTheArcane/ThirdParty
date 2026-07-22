from thirdparty.recipe import RecipeBase


def cross_building(recipe: RecipeBase, skip_x64_x86: bool = False) -> bool:
    """
    Check if we are cross building comparing the *build* and *host* settings. Returns ``True``
    in the case that we are cross-building.

    :param recipe: The current recipe object. Always use ``self``.
    :param skip_x64_x86: Do not consider cross building when building to 32 bits from 64 bits:
           x86_64 to x86, sparcv9 to sparc or ppc64 to ppc32
    :return: ``bool`` value from ``tools.build.cross_building:cross_build`` if exists, otherwise,
             it returns ``True`` if we are cross-building, else, ``False``.
    """
    cross_build = recipe.conf.tools.build.cross_building.cross_build
    if cross_build is not None:
        return cross_build

    build_os = recipe.settings_build.os
    build_arch = recipe.settings_build.arch
    host_os = recipe.settings.os
    host_arch = recipe.settings.arch

    if skip_x64_x86 and host_os is not None and (build_os == host_os) and host_arch is not None and (  # pyright: ignore[reportUnnecessaryComparison]  # settings os/arch typed str; keep defensive None guard
        (build_arch == "x86_64") and (host_arch == "x86") or (build_arch == "sparcv9") and (host_arch == "sparc") or (build_arch == "ppc64") and (host_arch == "ppc32")):
        return False

    if host_os is not None and (build_os != host_os):  # pyright: ignore[reportUnnecessaryComparison]  # settings.os typed str; keep defensive None guard
        return True
    if host_arch is not None and (build_arch != host_arch):  # pyright: ignore[reportUnnecessaryComparison]  # settings.arch typed str; keep defensive None guard
        return True

    return False


def can_run(recipe: RecipeBase) -> bool:
    """
    Validates whether is possible to run a non-native app on the same architecture.
    It's a useful feature for the case your architecture can run more than one target.
    For instance, Mac M1 machines can run both `armv8` and `x86_64`.

    :param recipe: The current recipe object. Always use ``self``.
    :return: ``bool`` value from ``tools.build.cross_building:can_run`` if exists, otherwise,
             it returns ``False`` if we are cross-building, else, ``True``.
    """
    # Issue related: upstream issue 11035
    allowed = recipe.conf.tools.build.cross_building.can_run
    if allowed is None:
        return not cross_building(recipe)
    return allowed
