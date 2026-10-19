"""Every documented example runs and shows what it claims.

The docstring examples run through ``doctest`` on the package and on each private module.
The ``python`` blocks of README.md and GUIDE.md run statement by statement; an expression
followed by comment lines must have that ``repr``, a trailing ``# True``, ``# False``,
or ``# None`` must match, and ``# raises Name`` must raise that error.
"""

from __future__ import annotations

import ast
import doctest
import importlib
import io
import pkgutil
import tokenize
from types import ModuleType, SimpleNamespace

import pytest
from docblocks import python_blocks

import httprange as hr

PRIVATE = sorted(info.name for info in pkgutil.iter_modules(hr.__path__) if info.name[0] == "_")


def _run_doctests(module: ModuleType) -> doctest.TestResults:
    return doctest.testmod(module, optionflags=doctest.ELLIPSIS)


def test_every_public_example_runs_from_the_package() -> None:
    finder = doctest.DocTestFinder()
    for name in hr.__all__:
        found = finder.find(getattr(hr, name), name, module=hr)
        assert sum(len(test.examples) for test in found) > 0, name
    failed, attempted = _run_doctests(hr)
    assert failed == 0
    assert attempted >= 75


@pytest.mark.parametrize("name", PRIVATE)
def test_every_private_module_example_runs(name: str) -> None:
    module = importlib.import_module(f"httprange.{name}")
    assert _run_doctests(module).failed == 0


def _comments(source: str) -> dict[int, str]:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return {tok.start[0]: tok.string[1:].strip() for tok in tokens if tok.type == tokenize.COMMENT}


def _claim(comment: str) -> object:
    """The value a trailing comment claims, or ``...`` when it claims none."""
    word = comment.split()[0].rstrip(",:;") if comment else ""
    return {"True": True, "False": False, "None": None}.get(word, ...)


def run_block(source: str, namespace: dict[str, object]) -> int:
    """Run ``source`` statement by statement and check its claims; return how many."""
    lines = source.splitlines()
    comments = _comments(source)
    checked = 0
    for node in ast.parse(source).body:
        end = node.end_lineno or node.lineno
        if not isinstance(node, ast.Expr):
            exec(compile(ast.Module([node], []), "<doc>", "exec"), namespace)
            continue
        trailing = comments.get(end, "")
        if trailing.startswith("raises "):
            error = getattr(hr, trailing.split()[1])
            with pytest.raises(error):
                eval(compile(ast.Expression(node.value), "<doc>", "eval"), namespace)
            checked += 1
            continue
        value = eval(compile(ast.Expression(node.value), "<doc>", "eval"), namespace)
        following = []
        for line in lines[end:]:
            if not line.startswith("# "):
                break
            following.append(line[2:])
        if following:
            assert repr(value) == "\n".join(following), source
            checked += 1
        elif (claim := _claim(trailing)) is not ...:
            assert value == claim, (trailing, value)
            checked += 1
    return checked


def test_readme_examples_show_what_they_claim() -> None:
    quick, blocks = python_blocks("README.md")
    namespace: dict[str, object] = {"data": bytes(10000)}
    assert run_block(quick, namespace) >= 1
    decision = namespace["decision"]
    assert isinstance(decision, hr.RangeDecision)
    assert (decision.status, decision.content_range, decision.is_multipart) == (206, None, True)
    assert "body" in namespace
    assert run_block(blocks, {}) >= 8


def test_guide_examples_show_what_they_claim() -> None:
    handler, policy, client, if_range = python_blocks("GUIDE.md")
    run_block(handler, {})
    assert run_block(policy, {}) == 1
    sent = hr.build_multipart_byteranges(b"0123456789", [hr.ByteRange(0, 1), hr.ByteRange(8, 9)])
    response = SimpleNamespace(
        headers={"Content-Range": "bytes 0-1/10", "Content-Type": sent.content_type}
    )
    stored: list[tuple[object, bytes]] = []
    namespace = {"response": response, "body": sent.body, "store": lambda *a: stored.append(a)}
    run_block(client, namespace)
    assert stored == [(0, b"01"), (8, b"89")]
    assert run_block(if_range, {}) == 3


def test_readme_quick_start_comment_holds_for_every_status() -> None:
    for header, expected in (
        (None, None),
        ("bytes=0-0", "bytes 0-0/10000"),
        ("bytes=20000-", "bytes */10000"),
    ):
        decision = hr.evaluate_range_request(method="GET", range_header=header, length=10000)
        assert decision.content_range == expected
