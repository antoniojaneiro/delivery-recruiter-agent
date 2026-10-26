"""D63: the engine (package `screener`) knows nothing about a client (package `sazon` is Grupo Sazón's). The engine
never imports a client, and its code and comments carry none of a client's words."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "screener"
CLIENT_PACKAGES = {"sazon"}
FORBIDDEN_WORDS = re.compile(r"saz[oó]n|grupo|repartidor|licen[cs]|madrid|guadalajara|glovo|uber eats|rappi|delivery|driver"
                             r"|mexico|méxico|españa|spain", re.IGNORECASE)


def engine_files() -> list[Path]:
    return sorted(ENGINE.glob("*.py"))


def imported_packages(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
    return found


def test_the_engine_is_not_empty():
    assert {p.name for p in engine_files()} >= {"screening.py", "turn.py", "store.py", "phrasing.py", "spec.py"}


def test_the_engine_never_imports_a_client():
    leaks = {p.name: sorted(imported_packages(p) & CLIENT_PACKAGES) for p in engine_files()}
    assert {name: packages for name, packages in leaks.items() if packages} == {}


def test_the_engine_carries_no_clients_words():
    leaks = {}
    for path in engine_files():
        hits = sorted({m.group(0).lower() for m in FORBIDDEN_WORDS.finditer(path.read_text(encoding="utf-8"))})
        if hits:
            leaks[path.name] = hits
    assert leaks == {}


def test_the_second_client_in_the_tests_uses_only_the_engine():
    assert imported_packages(ROOT / "tests" / "toy_spec.py") & CLIENT_PACKAGES == set()


def test_a_client_package_holds_only_what_is_the_clients():
    client_files = {p.name for p in (ROOT / "sazon").glob("*.py")}
    assert not client_files & {"screening.py", "turn.py", "store.py", "phrasing.py", "session.py", "funnel.py"}
