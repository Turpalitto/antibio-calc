"""Every name used in a type annotation must actually be declared in its module.

Two defects of this class shipped, both hidden by PEP 563: ``from __future__ import
annotations`` makes annotations strings, so a name that is never imported does not fail at
import time and the code runs fine — until something evaluates the annotation
(``typing.get_type_hints``, a serialiser, ``pydantic``, a type checker) and raises
``NameError``.

* ``clinical_engine.review_workbench.dose_unit_audit.import_into_store`` annotated its
  parameter as ``ReviewStore`` without importing it;
* ``clinical_engine.bundles.loader.LoadedBundle`` annotated a field as
  ``ConformanceResult`` without importing it — and a plain import there would be circular,
  since ``conformance.py`` imports ``LoadedBundle`` back, so it needs ``TYPE_CHECKING``.

This is the same class as the shipped-JS defect where a branch read ``form.form_type``
instead of the loop variable: a reference to something that is not in scope, invisible
until something actually evaluates it.

The check is static (AST) rather than ``typing.get_type_hints`` on purpose. At runtime
``TYPE_CHECKING`` is ``False``, so the guarded import never executes and
``get_type_hints`` raises ``NameError`` for the *correct* pattern too — which makes it a
generator of false positives. ``clinical_engine.pipeline.StageContext`` already used
``TYPE_CHECKING`` correctly and still failed that way.
"""

from __future__ import annotations

import ast
import builtins
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".venv", "__pycache__", "node_modules", ".git", "generated"}

# Явно через модуль builtins: в импортируемом модуле __builtins__ оказывается
# словарём, и dir() от него возвращает методы словаря, а не int/str/list.
BUILTINS = set(dir(builtins)) | {"None", "True", "False", "self", "cls"}


def _declared_names(tree: ast.AST) -> set[str]:
    """Все имена, объявленные в модуле: импорты (включая TYPE_CHECKING), определения,
    присваивания, параметры, цели циклов и comprehensions."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.comprehension):
            for target in ast.walk(node.target):
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _annotation_names(annotation: ast.AST) -> list[str]:
    """Имена из аннотации, включая строковые (``"Foo | None"``)."""
    found: list[str] = []
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name):
            found.append(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for part in (
                node.value.replace("[", " ").replace("]", " ")
                .replace("|", " ").replace(",", " ").split()
            ):
                part = part.strip().split(".")[0]
                if part and part.isidentifier():
                    found.append(part)
    return found


def _iter_annotations(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotations = [
                arg.annotation
                for arg in node.args.args + node.args.kwonlyargs
                if arg.annotation is not None
            ]
            if node.args.vararg and node.args.vararg.annotation is not None:
                annotations.append(node.args.vararg.annotation)
            if node.args.kwarg and node.args.kwarg.annotation is not None:
                annotations.append(node.args.kwarg.annotation)
            if node.returns is not None:
                annotations.append(node.returns)
            for annotation in annotations:
                yield node.name, annotation
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
            yield "<class or module body>", node.annotation


def _python_files() -> list[Path]:
    return [
        path
        for path in sorted(ROOT.rglob("*.py"))
        if not any(part in SKIP_PARTS for part in path.parts)
    ]


def test_the_repository_actually_contains_python_to_check() -> None:
    """Предусловие: если обход перестанет находить файлы, тест потеряет смысл."""
    files = _python_files()
    assert len(files) > 300, f"ожидалось более 300 файлов, найдено {len(files)}"
    assert any("clinical_engine" in str(p) for p in files)
    assert any("src" in p.parts for p in files)


def test_every_annotation_name_is_declared_in_its_module() -> None:
    """Ни одно имя в аннотации не должно быть необъявленным.

    Обход статический: ``typing.get_type_hints`` не годится, потому что в рантайме
    ``TYPE_CHECKING`` ложен и корректный паттерн тоже падает с ``NameError``.
    """
    undeclared: list[str] = []
    checked = 0

    for path in _python_files():
        # utf-8-sig: в репозитории есть файлы с BOM, ast.parse на них падает
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        declared = _declared_names(tree)
        for owner, annotation in _iter_annotations(tree):
            checked += 1
            for name in set(_annotation_names(annotation)):
                if name in declared or name in BUILTINS:
                    continue
                undeclared.append(f"{path.relative_to(ROOT)} :: {owner} -> {name}")

    assert checked > 5000, f"ожидалось более 5000 аннотаций, проверено {checked}"
    assert undeclared == [], (
        "имена в аннотациях не объявлены в своих модулях "
        "(нужен импорт, при цикле — под TYPE_CHECKING):\n  " + "\n  ".join(undeclared)
    )


@pytest.mark.parametrize(
    "module_path, attribute, expected",
    [
        (
            "clinical_engine/review_workbench/dose_unit_audit.py",
            "import_into_store",
            "ReviewStore",
        ),
        ("clinical_engine/bundles/loader.py", "LoadedBundle", "ConformanceResult"),
    ],
)
def test_the_two_known_cases_now_declare_their_names(
    module_path: str, attribute: str, expected: str
) -> None:
    """Оба найденных случая закреплены отдельно — чтобы правку не откатили."""
    source = (ROOT / module_path).read_text(encoding="utf-8-sig")
    assert expected in source, f"{expected} пропал из {module_path}"
    # Имя обязано быть именно импортировано, а не просто упомянуто в комментарии.
    assert f"import {expected}" in source, (
        f"{expected} в {module_path} упомянут, но не импортирован"
    )
