import os

from thirdparty.recipe import RecipeBase


def relativize_path(
    path: str,
    recipe: RecipeBase,
    placeholder: str,
    normalize: bool = True) -> str:
    """
    relative path from the "generators_folder" to "path", asuming the root file, like
    recipe_toolchain.cmake will be directly in the "generators_folder"
    """
    generators_folder = os.fspath(recipe.folders.generators)
    base_common_folder = generators_folder
    if not base_common_folder or not os.path.isabs(base_common_folder):
        return path
    try:
        common_path = os.path.commonpath([os.fspath(path), generators_folder, base_common_folder])
        if common_path.replace("\\", "/") == base_common_folder.replace("\\", "/"):
            rel_path = os.path.relpath(path, generators_folder)
            new_path = os.path.join(placeholder, rel_path)
            return new_path.replace("\\", "/") if normalize else new_path
    except ValueError:  # In case the unit in Windows is different, path cannot be made relative
        pass
    return path
