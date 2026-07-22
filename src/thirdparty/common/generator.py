from typing import ParamSpec, Protocol, TypeVar

from thirdparty.recipe import RecipeBase


_GenerateArgs = ParamSpec("_GenerateArgs")
_GenerateResult = TypeVar("_GenerateResult", covariant=True)


class Generator(Protocol[_GenerateArgs, _GenerateResult]):
    def generate(
        self,
        *args: _GenerateArgs.args,
        **kwargs: _GenerateArgs.kwargs,
    ) -> _GenerateResult: ...


class GeneratorClass(Protocol[_GenerateArgs, _GenerateResult]):
    def __call__(self, __recipe: RecipeBase) -> Generator[_GenerateArgs, _GenerateResult]: ...


def generate(
    recipe: RecipeBase,
    generator_class: GeneratorClass[_GenerateArgs, _GenerateResult],
    *args: _GenerateArgs.args,
    **kwargs: _GenerateArgs.kwargs) -> _GenerateResult:
    return generator_class(recipe).generate(*args, **kwargs)
