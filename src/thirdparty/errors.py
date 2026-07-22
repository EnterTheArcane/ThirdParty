class RecipeException(Exception):
    """Generic recipe exception."""


class RecipeInvalidConfiguration(RecipeException):
    """
    This binary, for the requested configuration and package-id cannot be built
    """
    pass


__all__ = [
    "RecipeException", "RecipeInvalidConfiguration",
]
