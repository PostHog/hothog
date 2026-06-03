from hothog.dominators import DominatorTree


def test_diamond_idom_is_shared_entry():
    # a -> b -> d, a -> c -> d, d -> e   (d reachable two ways; e only via d)
    succ = {"a": {"b", "c"}, "b": {"d"}, "c": {"d"}, "d": {"e"}}
    dom = DominatorTree(succ, roots=["a"])
    # e is dominated by d (its sole path), so cutting at d removes e.
    chain = dom.cut_chain(["e"])
    assert chain[0] == "e"
    assert "d" in chain and "a" in chain
    deepest_above = next(c for c in chain if c != "e")
    assert deepest_above == "d"


def test_single_cut_point_above_multiple_importers():
    # a -> m, m -> x, m -> y, x -> lib, y -> lib  (lib imported by x and y, both funnel through m)
    succ = {"a": {"m"}, "m": {"x", "y"}, "x": {"lib"}, "y": {"lib"}}
    dom = DominatorTree(succ, roots=["a"])
    chain = dom.cut_chain(["x", "y"])  # the lib's two importers
    cut = next((c for c in chain if c not in ("x", "y")), None)
    assert cut == "m"  # one defer at m removes the whole subtree


def test_lca_of_library_module_set():
    succ = {"a": {"m"}, "m": {"x", "y"}, "x": {"lib"}, "y": {"lib"}}
    dom = DominatorTree(succ, roots=["a"])
    assert dom.lca("x", "y") == "m"
