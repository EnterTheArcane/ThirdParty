import graphlib
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thirdparty._internal.graph import Graph, Node


def _graph(nodes: list[Node]) -> Graph:
    return Graph({n.name: n for n in nodes})


class TopoOrderTests(unittest.TestCase):
    def test_self_tool_require_is_not_a_cycle(self):
        # qt cross-compile bootstrap: requires_tool itself.  The self tool-edge must be
        # dropped so ordering succeeds and qt is emitted once, after its real dep.
        g = _graph([
            Node("qt", "6.0", host_deps=["zlib"], tool_deps=["qt"]),
            Node("zlib", "1.3"),
        ])
        order = g.topo_order()
        self.assertEqual(order.count("qt"), 1)
        self.assertEqual(order, ["zlib", "qt"])

    def test_normal_chain_orders_deps_first(self):
        # a -> b -> c, plus ties broken alphabetically.
        g = _graph([
            Node("a", "1", host_deps=["b"]),
            Node("b", "1", host_deps=["c"]),
            Node("c", "1"),
        ])
        self.assertEqual(g.topo_order(), ["c", "b", "a"])

    def test_external_deps_ignored(self):
        # A dep not present in the graph imposes no ordering constraint.
        g = _graph([Node("a", "1", host_deps=["not_in_graph"])])
        self.assertEqual(g.topo_order(), ["a"])

    def test_self_host_require_still_raises(self):
        # A self *host* require is a genuine recipe bug and must still be a cycle.
        g = _graph([Node("x", "1", host_deps=["x"])])
        with self.assertRaises(graphlib.CycleError):
            g.topo_order()

    def test_mutual_tool_cycle_still_raises(self):
        # Only direct self tool-edges are excused; a mutual cycle is still an error.
        g = _graph([
            Node("a", "1", tool_deps=["b"]),
            Node("b", "1", tool_deps=["a"]),
        ])
        with self.assertRaises(graphlib.CycleError):
            g.topo_order()


if __name__ == "__main__":
    unittest.main()
