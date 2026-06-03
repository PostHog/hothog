from hothog.deferability import deferability


def test_function_body_only_is_easy():
    src = "import foo\ndef f():\n    return foo.bar()\n"
    assert deferability("foo", [src]) == ("easy(1)", 1)


def test_three_functions_is_many():
    src = "import foo\ndef a():\n    return foo.x()\ndef b():\n    return foo.y()\ndef c():\n    return foo.z()\n"
    verdict, n = deferability("foo", [src])
    assert verdict == "many(3)"
    assert n == 3


def test_base_class_is_blocked():
    src = "import foo\nclass X(foo.Base):\n    pass\n"
    assert deferability("foo", [src]) == ("BLOCKED:baseclass", 0)


def test_module_scope_use_is_blocked():
    src = "import foo\nVALUE = foo.compute()\n"
    assert deferability("foo", [src])[0] == "BLOCKED:modscope"


def test_annotation_only_with_future_is_lazy():
    src = "from __future__ import annotations\nimport foo\ndef f(x: foo.T) -> None:\n    pass\n"
    assert deferability("foo", [src]) == ("annot:lazy", 0)


def test_annotation_only_without_future_needs_str():
    src = "import foo\ndef f(x: foo.T) -> None:\n    pass\n"
    assert deferability("foo", [src]) == ("annot:needs-str", 0)


def test_test_only_short_circuits():
    src = "import fakeredis\nVALUE = fakeredis.thing()\n"  # would be modscope, but suppressed
    assert deferability("fakeredis", [src], test_only=frozenset({"fakeredis"})) == ("TEST-only", 0)


def test_aliased_import_is_tracked():
    src = "import foo as bar\ndef f():\n    return bar.baz()\n"
    assert deferability("foo", [src]) == ("easy(1)", 1)


def test_unused_library_is_unknown():
    src = "import something_else\ndef f():\n    pass\n"
    assert deferability("foo", [src]) == ("?", 0)
