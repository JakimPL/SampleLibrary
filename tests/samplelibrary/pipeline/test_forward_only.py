from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

import samplelibrary.pipeline.scheduler

PIPELINE_ROOT: Final[Path] = Path(samplelibrary.pipeline.scheduler.__file__).parent
CORE_MODULES: Final[tuple[str, ...]] = ("scheduler.py", "execution.py", "scratch.py", "artifacts.py", "events.py")
# A file opened for appending closes as the block ends, and the interrupt watch puts the signal
# handlers back: neither writes anything a later run reads.
ALLOWED_CONTEXTS: Final[frozenset[str]] = frozenset({"open", "InterruptWatch"})
# The watch's own exit restores signal handlers, which is the one thing an exit may do here.
ALLOWED_EXITS: Final[frozenset[str]] = frozenset({"InterruptWatch"})


def _tree(module: str) -> ast.Module:
    return ast.parse((PIPELINE_ROOT / module).read_text(encoding="utf-8"))


def _called_name(expression: ast.expr) -> str:
    match expression:
        case ast.Call(func=ast.Name(id=name)) | ast.Call(func=ast.Attribute(attr=name)):
            return name
        case _:
            return ast.unparse(expression)


@pytest.mark.parametrize("module", CORE_MODULES)
def test_the_pipeline_core_makes_no_durable_effect_while_unwinding(module: str) -> None:
    """A run killed at any moment equals one stopped there only while nothing durable happens on the way out.

    So the core holds no `finally`, catches no `BaseException`, enters only contexts that write
    nothing a later run reads, and defines no exit beyond the interrupt watch's.
    """
    for node in ast.walk(_tree(module)):
        match node:
            case ast.Try(finalbody=finalbody) if finalbody:
                pytest.fail(f"{module}:{node.lineno} holds a finally block")
            case ast.ExceptHandler(type=None):
                pytest.fail(f"{module}:{node.lineno} catches everything")
            case ast.ExceptHandler(type=ast.Name(id="BaseException")):
                pytest.fail(f"{module}:{node.lineno} catches BaseException")
            case ast.With(items=items):
                entered = {_called_name(item.context_expr) for item in items}
                assert entered <= ALLOWED_CONTEXTS, f"{module}:{node.lineno} enters {sorted(entered)}"
            case ast.ClassDef(name=name, body=body) if name not in ALLOWED_EXITS:
                exits = [item for item in body if isinstance(item, ast.FunctionDef) and item.name == "__exit__"]
                assert not exits, f"{module}:{node.lineno} defines an exit for {name}"
