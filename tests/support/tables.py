"""Table tests. `table` reads like `pytest.mark.parametrize` but runs every row inside ONE test and, when some rows fail,
reports all of them together (the row, and why), so a table of a hundred inputs is one test and a failure still names its row.

Only for tests that need nothing built fresh for each row (no database, no app): pure functions and rules."""
import functools
import inspect


def table(argnames, rows):
    names = [n.strip() for n in argnames.split(",")] if isinstance(argnames, str) else list(argnames)

    def decorate(function):
        outside = [p for p in inspect.signature(function).parameters.values() if p.name not in names]

        @functools.wraps(function)
        def run_every_row(*args, **kwargs):
            failures = []
            for row in rows:
                values = getattr(row, "values", row)  # a pytest.param keeps its values
                values = values if len(names) > 1 else (values[0] if isinstance(values, tuple) and len(values) == 1 else values,)
                try:
                    function(*args, **kwargs, **dict(zip(names, values)))
                except Exception as error:  # an assertion, or anything the row made go wrong
                    failures.append(f"  {tuple(values)!r}: {type(error).__name__}: {str(error).splitlines()[0] if str(error) else ''}")
            assert not failures, f"{len(failures)} of {len(rows)} rows failed:\n" + "\n".join(failures)

        run_every_row.__signature__ = inspect.Signature(outside)  # pytest only supplies the fixtures, not the row's values
        return run_every_row

    return decorate
