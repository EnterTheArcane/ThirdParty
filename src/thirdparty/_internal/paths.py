import os
import platform
from pathlib import Path

from thirdparty.errors import RecipeException

if platform.system() == "Windows":
    def _recipe_expand_user(path: "str | os.PathLike[str]") -> str:
        """ wrapper to the original expanduser function, to workaround python returning
        verbatim %USERPROFILE% when some other app (git for windows) sets HOME envvar
        """
        path = str(path)
        if path[0] != "~":
            return path
        # In win these variables should exist and point to user directory, which
        # must exist.
        home = os.environ.get("HOME")
        try:
            # Problematic cases of wrong HOME variable
            # - HOME = %USERPROFILE% verbatim, as messed by some other tools
            # - MSYS console, that defines a different user home in /c/mingw/msys/users/xxx
            # In these cases, it is safe to remove it and rely on USERPROFILE directly
            if home and (not os.path.exists(home) or (os.getenv("MSYSTEM") and os.getenv("USERPROFILE"))):
                del os.environ["HOME"]
            result = os.path.expanduser(path)
        finally:
            if home is not None:
                os.environ["HOME"] = home
        return result
else:
    def _recipe_expand_user(path: "str | os.PathLike[str]") -> str:
        return os.path.expanduser(path)

DEFAULT_O3DE_PACKAGE_HOME = os.path.join(".o3de", "ThirdParty")


def find_file_walk_up(start: "str | os.PathLike[str]", filename: str, end: "str | os.PathLike[str] | None" = None) -> Path | None:
    path = Path(start)
    end = Path(end) if end else None
    while True:
        file = path / filename
        if file.is_file():
            return file
        if len(path.parts) == 1:  # finish at '/'
            break
        if end and path == end:
            break
        path = path.parent
    return None


def get_recipe_user_home():
    def _user_home_from_rc_file():
        try:
            rc_path = find_file_walk_up(os.getcwd(), ".thirdpartyrc")
            if rc_path is None:
                return None

            with open(rc_path) as rc_file:
                values = {k: str(v) for k, v in (line.split("=") for line in rc_file.read().splitlines() if not line.startswith("#"))}

            recipe_home = values["recipe_home"]
            # check if it's a local folder
            if recipe_home[:2] in ("./", ".\\") or recipe_home.startswith(".."):
                recipe_home = rc_path.parent.absolute() / recipe_home
            return recipe_home
        except (OSError, KeyError, TypeError):
            return None

    user_home = _user_home_from_rc_file() or os.getenv("O3DE_PACKAGE_HOME")
    if user_home is None:
        # the default, in the user home
        user_home = os.path.join(_recipe_expand_user("~"), DEFAULT_O3DE_PACKAGE_HOME)
    else:  # Do an expansion, just in case the user is using ~/something/here
        user_home = _recipe_expand_user(user_home)
    if not os.path.isabs(user_home):
        raise RecipeException(
            "Invalid O3DE_PACKAGE_HOME value '%s', "
            "please specify an absolute or path starting with ~/ "
            "(relative to user home)" % user_home)
    return user_home
