"""A small ABNF reader (RFC 5234, with RFC 7405 strings) for grammar-derived oracles.

The rules are read from the fetched RFC texts and turned into regular expressions and
random sentences. Nothing here comes from the library under test.
"""

from __future__ import annotations

import random
import re
from typing import Any

_TOKEN = re.compile(
    r"\s*(?:(?P<num>%[xd][0-9A-Fa-f]+(?:-[0-9A-Fa-f]+|(?:\.[0-9A-Fa-f]+)+)?)"
    r'|(?P<str>(?:%[si])?"[^"]*")|(?P<rep>\d*\*\d*|\d+)|(?P<name>[A-Za-z][A-Za-z0-9-]*)'
    r"|(?P<sym>[/()\[\]])|(?P<prose><[^>]*>))"
)
# ("alt", [nodes]), ("cat", [nodes]), ("rep", low, high or -1, node), ("chars", [(low, high)]),
# ("str", text, case_sensitive), ("rule", name), ("prose", text)
Node = tuple[Any, ...]


def strip_comment(line: str) -> str:
    """The line without its ``;`` comment; a ``;`` inside a quoted string stays."""
    quoted = False
    for index, char in enumerate(line):
        if char == '"':
            quoted = not quoted
        elif char == ";" and not quoted:
            return line[:index]
    return line


def read_rules(text: str, indent: int) -> dict[str, Node]:
    """Rules written as ``<indent spaces>name = ...`` with deeper continuation lines."""
    rules: dict[str, str] = {}
    name = ""
    for line in text.split("\n"):
        start = re.match(rf"^ {{{indent}}}([A-Za-z][A-Za-z0-9-]*) +=(?!/) *(.*)$", line)
        if start:
            name = start[1].lower()
            rules[name] = strip_comment(start[2])
        elif name and line.startswith(" " * (indent + 1)):
            rules[name] += " " + strip_comment(line)
        elif line.strip():
            name = ""
    return {key: parse(value) for key, value in rules.items()}


def parse(text: str) -> Node:
    tokens = []
    position = 0
    while position < len(text.rstrip()):
        match = _TOKEN.match(text, position)
        if match is None or match.end() == position:
            raise ValueError(f"cannot read ABNF at {text[position:]!r}")
        assert match.lastgroup is not None
        tokens.append((match.lastgroup, match[match.lastgroup]))
        position = match.end()
    node, index = _alternation(tokens, 0)
    if index != len(tokens):
        raise ValueError(f"trailing ABNF in {text!r}")
    return node


def _alternation(tokens: list[tuple[str, str]], index: int) -> tuple[Node, int]:
    items = []
    node, index = _concatenation(tokens, index)
    items.append(node)
    while index < len(tokens) and tokens[index] == ("sym", "/"):
        node, index = _concatenation(tokens, index + 1)
        items.append(node)
    return (("alt", items) if len(items) > 1 else items[0]), index


def _concatenation(tokens: list[tuple[str, str]], index: int) -> tuple[Node, int]:
    items = []
    while index < len(tokens) and tokens[index] not in (("sym", "/"), ("sym", ")"), ("sym", "]")):
        low = high = 1
        if tokens[index][0] == "rep":
            text = tokens[index][1]
            if "*" in text:
                first, last = text.split("*")
                low, high = int(first or 0), (int(last) if last else -1)
            else:
                low = high = int(text)
            index += 1
        node, index = _element(tokens, index)
        items.append(node if (low, high) == (1, 1) else ("rep", low, high, node))
    return (("cat", items) if len(items) != 1 else items[0]), index


def _element(tokens: list[tuple[str, str]], index: int) -> tuple[Node, int]:
    kind, text = tokens[index]
    if kind == "name":
        return ("rule", text.lower()), index + 1
    if kind == "prose":
        return ("prose", text), index + 1
    if kind == "str":
        return ("str", text[text.index('"') + 1 : -1], text.startswith("%s")), index + 1
    if kind == "num":
        base = 16 if text[1] == "x" else 10
        if "-" in text:
            low, high = text[2:].split("-")
            return ("chars", [(int(low, base), int(high, base))]), index + 1
        codes = [int(part, base) for part in text[2:].split(".")]
        items = [("chars", [(code, code)]) for code in codes]
        return (items[0] if len(items) == 1 else ("cat", items)), index + 1
    if text in "([":
        node, index = _alternation(tokens, index + 1)
        assert tokens[index] == ("sym", ")" if text == "(" else "]"), tokens[index:]
        return (node if text == "(" else ("rep", 0, 1, node)), index + 1
    raise ValueError(f"unexpected ABNF token {text!r}")


def regex(node: Node, rules: dict[str, Node], stack: tuple[str, ...] = ()) -> str:
    """A Python regular expression for ``node``; rules are inlined (no recursion)."""
    kind = node[0]
    if kind == "alt":
        return "(?:" + "|".join(regex(item, rules, stack) for item in node[1]) + ")"
    if kind == "cat":
        return "".join(regex(item, rules, stack) for item in node[1])
    if kind == "rep":
        low, high = node[1], node[2]
        count = {(0, -1): "*", (1, -1): "+", (0, 1): "?"}.get((low, high))
        count = count or "{" + str(low) + "," + ("" if high < 0 else str(high)) + "}"
        return "(?:" + regex(node[3], rules, stack) + ")" + count
    if kind == "chars":
        return "[" + "".join(_span(low, high) for low, high in node[1]) + "]"
    if kind == "str":
        return "".join(_char(char, node[2]) for char in node[1])
    if kind == "prose":
        raise ValueError(f"a prose rule has no grammar: {node[1]}")
    name = node[1]
    assert name not in stack, f"recursive rule {name}"
    return "(?:" + regex(rules[name], rules, (*stack, name)) + ")"


def _span(low: int, high: int) -> str:
    return f"\\x{low:02x}" if low == high else f"\\x{low:02x}-\\x{high:02x}"


def _char(char: str, sensitive: bool) -> str:
    if char.isascii() and char.isalpha() and not sensitive:
        return f"[{char.lower()}{char.upper()}]"
    return re.escape(char)


def sentence(node: Node, rules: dict[str, Node], rng: random.Random) -> str:
    """A random string the grammar of ``node`` accepts."""
    kind = node[0]
    if kind == "alt":
        return sentence(rng.choice(node[1]), rules, rng)
    if kind == "cat":
        return "".join(sentence(item, rules, rng) for item in node[1])
    if kind == "rep":
        low, high = node[1], node[2]
        top = high if high >= 0 else low + rng.choice((1, 2, 3, 3, 4, 8, 25))
        return "".join(sentence(node[3], rules, rng) for _ in range(rng.randint(low, top)))
    if kind == "chars":
        low, high = rng.choice(node[1])
        return chr(rng.randint(low, high))
    if kind == "str":
        text = node[1]
        return text if node[2] else "".join(rng.choice((c.lower(), c.upper())) for c in text)
    if kind == "prose":
        raise ValueError(f"a prose rule has no grammar: {node[1]}")
    return sentence(rules[node[1]], rules, rng)
