import traceback
from contextlib import contextmanager
from typing import Any

from thirdparty.errors import RecipeException, RecipeInvalidConfiguration
from thirdparty.recipe import RecipeBase


@contextmanager
def recipe_remove_attr(recipe: RecipeBase, names: Any, method: str):
    """ remove some self.xxxx attribute from the class, so it raises an exception if used
    within a given recipe method
    """
    original_class = type(recipe)

    def _prop(attr_name: str):
        def _m(_: Any):
            raise RecipeException(f"'self.{attr_name}' access in '{method}()' method is forbidden")

        return property(_m)

    try:
        new_class = type(original_class.__name__, (original_class,), {})
        recipe.__class__ = new_class
        for name in names:
            setattr(new_class, name, _prop(name))
        yield
    finally:
        recipe.__class__ = original_class


@contextmanager
def recipe_exception_formatter(recipe: RecipeBase, funcname: str):
    """
    Decorator to throw an exception formatted with the line of the recipe where the error ocurrs.
    """
    try:
        yield
    except RecipeInvalidConfiguration as exc:
        # TODO: This is never called from `recipe.validate()` but could be called from others
        msg = f"{str(recipe)}: Invalid configuration: {exc}"
        raise RecipeInvalidConfiguration(msg)
    except Exception as exc:
        m = scoped_traceback(f"{recipe}: Error in {funcname}() method", exc, scope="recipe.py")
        from thirdparty._internal.output import LEVEL_DEBUG, Output
        if Output.level_allowed(LEVEL_DEBUG):
            m = traceback.format_exc() + "\n" + m
        raise RecipeException(m)


def scoped_traceback(header_msg: str, exception: Exception, scope: str) -> str:
    """
    It will iterate the traceback lines, when it finds that the source code is inside the users
    recipe it "start recording" the messages, when the trace exits the recipe we return
    the traces.
    """
    import sys
    content_lines: list[str] = []
    try:
        scope_reached = False
        tb = sys.exc_info()[2]
        index = 0

        while True:  # If out of index will raise and will be captured later
            # 40 levels of nested functions max, get the latest
            filepath, line, name, contents = traceback.extract_tb(tb, 40)[index]
            filepath = filepath.replace("\\", "/")
            if scope not in filepath:  # Avoid show trace from internal recipe source code
                if scope_reached:  # The error goes to internal code, exit print
                    break
            else:
                if not scope_reached:  # First line
                    msg = f"{header_msg}, line {line}\n\t{contents}"
                else:
                    msg = (f"while calling '{name}', line {line}\n\t{contents}" if line else "\n\t%s" % contents)
                content_lines.append(msg)
                scope_reached = True
            index += 1
    except IndexError:
        pass
    ret = "\n".join(content_lines)
    ret += "\n\t%s: %s" % (exception.__class__.__name__, str(exception))
    return ret


class ConnectionErrorException(RecipeException):
    pass


class InternalErrorException(RecipeException):
    pass


class RequestErrorException(RecipeException):
    pass


class AuthenticationException(RecipeException):  # 401
    pass


class ForbiddenException(RecipeException):  # 403
    pass


class NotFoundException(RecipeException):  # 404
    pass


class RecipeNotFoundException(NotFoundException):
    def __init__(self, ref: str):
        super().__init__(f"Recipe not found: '{ref}'")


class PackageNotFoundException(NotFoundException):
    def __init__(self, pref: str):
        super().__init__(f"Binary package not found: '{pref}'")


EXCEPTION_CODE_MAPPING = {
    InternalErrorException: 500,
    RequestErrorException: 400,
    AuthenticationException: 401,
    ForbiddenException: 403,
    NotFoundException: 404,
    RecipeNotFoundException: 404,
    PackageNotFoundException: 404,
}
