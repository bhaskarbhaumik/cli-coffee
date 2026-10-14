#!/usr/bin/env python3
"""Fail if a Nerd Font glyph is written as a literal character in code.

The panels are drawn with Private Use Area codepoints. No editor, terminal or
diff viewer renders them reliably, and several tools will happily substitute or
drop one — which changes what the dashboard looks like without changing
anything a reviewer can see. Writing them as ``\\uXXXX`` / ``\\UXXXXXXXX``
escapes makes that class of accident impossible to miss.

Comments and docstrings are exempt: a glyph there is documentation, and it
cannot reach the screen.

The check works by finding the source spans of comments and docstrings and
then scanning the raw text outside them. It deliberately does not inspect
string tokens directly: PEP 701 split f-strings into ``FSTRING_START`` /
``FSTRING_MIDDLE`` / ``FSTRING_END`` in Python 3.12, so a token-type test
passes vacuously on new interpreters and catches everything on old ones. Every
glyph in this project lives in an f-string.

Usage:
    python3 scripts/check_glyph_escapes.py [FILE ...]

With no arguments, checks every module under ``src/coffee/``.
"""

from __future__ import annotations

import ast
import io
import sys
import tokenize
from pathlib import Path

#: Unicode ranges used for glyphs that carry no standard meaning.
PRIVATE_USE_RANGES = (
    (0xE000, 0xF8FF),  # Basic Multilingual Plane PUA
    (0xF0000, 0xFFFFD),  # Supplementary PUA-A
    (0x100000, 0x10FFFD),  # Supplementary PUA-B
)

DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "src" / "coffee"

Position = tuple[int, int]  # (1-based row, 0-based column)
Span = tuple[Position, Position]  # half-open [start, end)


def is_private_use(char: str) -> bool:
    """Whether *char* is a Private Use Area codepoint."""
    point = ord(char)
    return any(low <= point <= high for low, high in PRIVATE_USE_RANGES)


def escape_for(char: str) -> str:
    """The Python escape that should be written instead of *char*."""
    point = ord(char)
    return f"\\u{point:04x}" if point <= 0xFFFF else f"\\U{point:08x}"


def _comment_spans(source: str) -> list[Span]:
    """Source spans of every comment. Reported as one token on all versions."""
    spans: list[Span] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                spans.append((token.start, token.end))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass  # a real syntax error is compileall's job to report
    return spans


def _docstring_spans(tree: ast.AST) -> list[Span]:
    """Source spans of every module, class and function docstring."""
    spans: list[Span] = []
    for node in ast.walk(tree):
        # A tuple, not a PEP 604 union: this script runs under whatever
        # `python3` the hook or the runner happens to have.
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
            continue
        constant = first.value
        if not isinstance(constant.value, str):
            continue
        if constant.end_lineno is None or constant.end_col_offset is None:
            continue
        spans.append(
            ((constant.lineno, constant.col_offset), (constant.end_lineno, constant.end_col_offset))
        )
    return spans


def _within(position: Position, spans: list[Span]) -> bool:
    """Whether *position* falls inside any half-open span."""
    return any(start <= position < end for start, end in spans)


def exempt_spans(source: str, path: Path) -> list[Span] | None:
    """Spans a literal glyph is allowed in, or None if the file will not parse."""
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return None
    return _comment_spans(source) + _docstring_spans(tree)


def find_literals(source: str, path: Path) -> list[tuple[Position, str]]:
    """Every literal glyph outside a comment or docstring."""
    spans = exempt_spans(source, path)
    if spans is None:
        return []
    found: list[tuple[Position, str]] = []
    for row, line in enumerate(source.splitlines(), start=1):
        for column, char in enumerate(line):
            if is_private_use(char) and not _within((row, column), spans):
                found.append(((row, column), char))
    return found


def check(path: Path) -> list[str]:
    """One message per literal glyph in *path*."""
    source = path.read_text(encoding="utf-8")
    return [
        f"{path}:{row}:{column + 1}: literal U+{ord(char):04X} — write it as {escape_for(char)}"
        for (row, column), char in find_literals(source, path)
    ]


def fix(path: Path) -> int:
    """Rewrite every literal glyph in *path* as an escape. Returns the count."""
    source = path.read_text(encoding="utf-8")
    found = find_literals(source, path)
    if not found:
        return 0
    lines = source.splitlines(keepends=True)
    for (row, column), char in reversed(found):  # back to front, so columns hold
        line = lines[row - 1]
        lines[row - 1] = line[:column] + escape_for(char) + line[column + 1 :]
    path.write_text("".join(lines), encoding="utf-8")
    return len(found)


def main(argv: list[str]) -> int:
    args = list(argv)
    apply_fix = False
    for flag in ("--fix", "-f"):
        if flag in args:
            args.remove(flag)
            apply_fix = True

    paths = [Path(a) for a in args] or sorted(DEFAULT_ROOT.glob("*.py"))
    paths = [p for p in paths if p.suffix == ".py" and p.is_file()]
    if not paths:
        print(f"no Python files to check under {DEFAULT_ROOT}", file=sys.stderr)
        return 1

    if apply_fix:
        total = 0
        for path in paths:
            count = fix(path)
            if count:
                print(f"{path}: escaped {count} glyph(s)")
                total += count
        print(f"{total} glyph(s) rewritten")
        return 0

    problems = [message for path in paths for message in check(path)]
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(
            f"\n{len(problems)} literal glyph(s). These are Private Use Area codepoints: write "
            "them as escapes so a transcription slip cannot change the display invisibly. "
            "Run `python3 scripts/check_glyph_escapes.py --fix`. See CONTRIBUTING.md.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
