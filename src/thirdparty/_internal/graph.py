from graphlib import TopologicalSorter
from pathlib import Path  # noqa: F401  (annotation only)

from thirdparty.recipe import RecipeBase


# Build contexts.
CONTEXT_HOST = "host"
CONTEXT_BUILD = "build"


class Node:
    """A node in the dependency graph: one recipe's identity and its direct dependencies."""

    def __init__(
        self, name: str, version: str, recipe_cls: "type[RecipeBase] | None" = None, host_deps: "list[str] | None" = None, tool_deps: "list[str] | None" = None, *, context: str = CONTEXT_HOST) -> None:
        self._name: str = name
        self._version: str = version
        self.recipe_cls: "type[RecipeBase] | None" = recipe_cls
        self.host_deps: list[str] = list(host_deps or [])
        self.tool_deps: list[str] = list(tool_deps or [])
        self.context: str = context

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    @property
    def all_deps(self) -> list[str]:
        return self.host_deps + self.tool_deps


COMPLETE_MARKER = ".complete"
MANIFEST = "manifest.json"


def package_root(build_root: Path, name: str, package_id: str) -> Path:
    """Output folder for a build, keyed by *package_id* (not version): ``build/<name>/<package_id>``."""
    return build_root / name / package_id


def read_manifest(build_root: Path, name: str, package_id: str) -> "dict[str, object] | None":
    import json
    path = package_root(build_root, name, package_id) / MANIFEST
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_manifest(build_root: Path, name: str, version: str, package_id: str) -> None:
    """Write ``manifest.json`` once when the folder is created; never updated (no completion flag)."""
    import json
    root = package_root(build_root, name, package_id)
    root.mkdir(parents=True, exist_ok=True)
    path = root / MANIFEST
    if path.exists():
        return
    path.write_text(
        json.dumps({"name": name, "version": str(version), "package_id": package_id}, indent=2),
        encoding="utf-8")


def invalidate_stale(build_root: Path, name: str, version: str, package_id: str) -> None:
    """Wipe the whole ``<package_id>`` folder if its manifest records a different version."""
    import shutil
    manifest = read_manifest(build_root, name, package_id)
    if manifest is not None and manifest.get("version") != str(version):
        shutil.rmtree(package_root(build_root, name, package_id), ignore_errors=True)


def is_built(
    build_root: Path,
    name: str,
    version: str,
    package_id: str) -> bool:
    """True if *version* is fully built for *package_id* (``build/.complete`` + matching manifest)."""
    root = package_root(build_root, name, package_id)
    if not (root / "build" / COMPLETE_MARKER).is_file():
        return False
    manifest = read_manifest(build_root, name, package_id)
    return manifest is not None and manifest.get("version") == str(version)



def discover_requires(recipe: RecipeBase) -> tuple[list[str], list[str]]:
    """Drive the recipe's config phase and return ``(host_dep_names, tool_dep_names)``.

    host_dep_names - regular library dependencies (build=False)
    tool_dep_names - requires_tool (build=True)

    The whole config phase (configure + default auto-fPIC handling +
    requirements) is delegated to ``run_configure_method``.  Errors are
    swallowed - dependency discovery is best-effort and must not abort graph resolution.
    """
    from thirdparty._internal.methods import run_configure_method

    try:
        run_configure_method(recipe)
    except Exception:
        pass
    host_names: list[str] = []
    tool_names: list[str] = []
    for req in recipe._requires:
        dep_name = str(req.name)
        if req.build:
            tool_names.append(dep_name)
        else:
            host_names.append(dep_name)
    return host_names, tool_names


class Graph:
    """A resolved dependency graph over a set of local recipes.

    Holds each recipe's direct host and tool dependencies (as :class:`Node` objects) and
    provides a stable topological ordering.  Reusable by ``build``, ``graph``, ``list``,
    and any other consumer that needs dependency-aware ordering.
    """

    def __init__(self, nodes: dict[str, Node]) -> None:
        self.nodes = nodes

    def __contains__(self, name: str) -> bool:
        return name in self.nodes

    def __getitem__(self, name: str) -> Node:
        return self.nodes[name]

    def names(self) -> list[str]:
        return list(self.nodes.keys())

    def topo_order(self) -> list[str]:
        """Return node names in dependency order (deps before dependants).

        Only edges between nodes present in this graph are considered; external
        dependencies are ignored for ordering.  Ties are broken alphabetically for
        deterministic output.

        A recipe that declares a ``requires_tool`` on *itself* is the cross-compile
        bootstrap pattern (e.g. ``qt``/``wayland`` need a native build of themselves
        before cross-building).  That self tool-edge is not a real cycle: the native copy
        lives in the build context and the target copy in the host context (see conan's
        two-context model), and the build executor (``_build_recipe``) builds the native
        copy first via its own recursion - keyed by ``(name, target_os, target_arch)`` -
        rather than as a second node here.  So a self *tool* edge is dropped for ordering
        and the single name-keyed node is emitted once.  A self *host* require is left in
        place so it still surfaces as a ``graphlib.CycleError`` (it is a real recipe bug).
        """
        sorter = TopologicalSorter(
            {name: [d for d in node.all_deps
                    if d in self.nodes and not (d == name and name in node.tool_deps)]
             for name, node in self.nodes.items()})
        sorter.prepare()

        order: list[str] = []
        ready = sorted(sorter.get_ready())
        while ready:
            node = ready.pop(0)
            order.append(node)
            sorter.done(node)
            ready.extend(sorter.get_ready())
            ready.sort()

        return order

    @staticmethod
    def build(
        recipes_root: Path, names: list[str], build_type: str, jobs: int | None = None, transitive: bool = False, target_os: str | None = None, target_arch: str | None = None, ) -> "Graph":
        """Resolve the dependencies of each recipe in ``names`` and return a graph.

        With ``transitive=False`` only the listed recipes become nodes.  With
        ``transitive=True`` the graph is expanded to the full transitive closure of the
        listed recipes (every reachable local dependency becomes a node too).

        ``target_os``/``target_arch`` select the platform used for requirement discovery
        (conditional ``requires`` may branch on ``settings.os``/``arch``).

        Recipes/deps that fail to load or probe are still included as nodes with no
        dependencies, so callers can report them rather than silently dropping them.
        """
        from thirdparty._internal.loader import (
            try_load_recipe_class, resolve_version, make_probe_recipe, )

        nodes: dict[str, Node] = {}
        queue: list[str] = list(names)
        seen: set[str] = set()
        while queue:
            name = queue.pop(0)
            if name in seen:
                continue
            seen.add(name)
            cls = try_load_recipe_class(recipes_root, name)
            if cls is None:
                nodes[name] = Node(name=name, version="?", recipe_cls=None)
                continue
            version = resolve_version(cls)
            try:
                probe = make_probe_recipe(
                    cls, recipes_root, name, version, build_type, jobs=jobs, target_os=target_os, target_arch=target_arch)
                host_deps, tool_deps = discover_requires(probe)
            except Exception:
                host_deps, tool_deps = [], []
            nodes[name] = Node(
                name=name, version=version, recipe_cls=cls, host_deps=host_deps, tool_deps=tool_deps)
            if transitive:
                for dep in host_deps + tool_deps:
                    if dep not in seen:
                        queue.append(dep)
        return Graph(nodes)
