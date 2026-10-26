"""D63: the engine knows nothing about a client. A client is a package of its own that the engine never imports,
and the engine's code and comments carry none of a client's words."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "sazon"

# What belongs to Grupo Sazón. Everything else in the package is the engine.
CLIENT_FILES = {
    "sazon_spec.py", "sazon_pack.py", "sazon_client.py", "sazon_fields.py", "sazon_validators.py",
    "sazon_chat.py", "sazon_reminders.py", "sazon_ui.py", "sazon_recruiter_view.py", "sazon_accounts.py", "config.py",
    "demo.py",
    "__init__.py",
}
CLIENT_MODULES = {Path(name).stem for name in CLIENT_FILES}
FORBIDDEN_WORDS = re.compile(r"saz[oó]n|grupo|repartidor|licen[cs]|madrid|guadalajara|glovo|uber eats|rappi|delivery|driver"
                             r"|mexico|méxico|españa|spain", re.IGNORECASE)


def engine_files() -> list[Path]:
    return sorted(p for p in PACKAGE.glob("*.py") if p.name not in CLIENT_FILES)


def imported_modules(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "sazon":
                found.update(alias.name for alias in node.names)
            elif node.module.startswith("sazon."):
                found.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            found.update(alias.name.split(".")[1] for alias in node.names if alias.name.startswith("sazon."))
    return found


def test_the_engine_is_not_empty():
    assert {p.name for p in engine_files()} >= {"screening.py", "turn.py", "store.py", "phrasing.py", "spec.py"}


def test_the_engine_never_imports_a_client_module():
    leaks = {p.name: sorted(imported_modules(p) & CLIENT_MODULES) for p in engine_files()}
    assert {name: modules for name, modules in leaks.items() if modules} == {}


PACKAGE_NAME = re.compile(r"\bsazon\b(?=\.| import)")  # the engine's own package name, until D63 renames it


def test_the_engine_carries_no_clients_words():
    leaks = {}
    for path in engine_files():
        text = PACKAGE_NAME.sub("", path.read_text(encoding="utf-8"))
        hits = sorted({m.group(0).lower() for m in FORBIDDEN_WORDS.finditer(text)})
        if hits:
            leaks[path.name] = hits
    assert leaks == {}


def test_the_second_client_in_the_tests_uses_only_the_engine():
    toy = ROOT / "tests" / "toy_spec.py"
    assert imported_modules(toy) & CLIENT_MODULES == set()
