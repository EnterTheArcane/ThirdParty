from dataclasses import dataclass

from thirdparty._internal.model.refs import RecipeReference


@dataclass(eq=False)  # eq=False: keep it mutable + custom (name, build) identity
class Requirement:
    """A single dependency declared by a recipe.

    Declared imperatively from a recipe's ``requirements()`` method via ``self.requires(...)``
    (regular library dep) or ``self.requires_tool(...)`` (build tool, ``build=True``).
    """

    ref: RecipeReference
    headers: bool = True   # dependency exposes headers to include
    libs: bool = True      # dependency exposes libraries to link
    build: bool = False    # build tool that runs on the build machine (e.g. cmake)
    run: bool = False      # dependency provides executables/shared libs needed at run time
    direct: bool = True    # a direct (vs transitively pulled) requirement
    skip: bool = False     # excluded from the consumer's effective dependency set

    @property
    def name(self) -> str:
        """Name of the recipe this requirement targets."""
        return self.ref.name

    def __hash__(self) -> int:
        return hash((self.ref.name, self.build))

    def __eq__(self, other: object) -> bool:
        # Two requirements are the same if they name the same package in the same context.
        return (isinstance(other, Requirement)
                and self.ref.name == other.ref.name and self.build == other.build)

    def __str__(self) -> str:
        return str(self.ref)


@dataclass(eq=False)  # inherits Requirement's (name, build) identity
class ToolRequirement(Requirement):
    """A build-tool requirement (e.g. cmake, nasm).

    Tools run on the build machine and expose neither headers nor libs.
    """

    headers: bool = False
    libs: bool = False
    build: bool = True
    run: bool = True
