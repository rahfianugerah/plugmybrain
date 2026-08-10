# The guards that matter: never write above the generated area, never ingest a secret.
from pathlib import Path

import pytest

from plugmybrain import config, ingest, promote


def test_namespace_is_the_lowercased_directory_name():
    assert config.namespace(Path("C:/some/Path/My-Project")) == "my-project"


def test_generated_path_stays_inside_the_generated_area():
    path = config.generated_path("code", "docs", "GRAPH_REPORT.md")
    assert path.is_relative_to(config.VAULT_GENERATED.resolve())


def test_generated_path_refuses_to_escape():
    with pytest.raises(ValueError):
        config.generated_path("..", "memory", "stolen.md")


@pytest.mark.parametrize(
    "name",
    [".env", ".env.local", "id_rsa.pem", "server.key", "credentials.json", "env-vars.yaml"],
)
def test_secret_filenames_are_excluded(name):
    assert config.is_excluded(Path("/project") / name)


@pytest.mark.parametrize("directory", ["keys", ".venv", "node_modules", ".git"])
def test_secret_directories_are_excluded(directory):
    assert config.is_excluded(Path("/project") / directory / "notes.md")


def test_ordinary_documents_are_not_excluded():
    assert not config.is_excluded(Path("/project/docs/commit.rules.md"))


def test_collect_documents_splits_included_from_skipped(tmp_path):
    (tmp_path / "keep.md").write_text("hello", encoding="utf-8")
    (tmp_path / "ignore.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=x", encoding="utf-8")
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "leak.md").write_text("secret", encoding="utf-8")

    included, skipped = config.collect_documents(tmp_path)

    # Source is Graphify's job, so .py is neither ingested nor reported as a blocked secret.
    assert [p.name for p in included] == ["keep.md"]
    assert {p.name for p in skipped} == {".env", "leak.md"}


def test_dimension_guard_matches_the_pgvector_index_ceiling():
    assert config.MAX_INDEXABLE_DIMENSIONS == 2000


# pgvector sizes IVFFlat at lists = rows / 1000, so a small table would get a one-list index,
# which is a sequential scan carrying index overhead. Exact search has to win below the
# threshold or the whole choice is theatre.
@pytest.mark.parametrize(
    ("rows", "expected"),
    [(0, "exact"), (500, "exact"), (9_999, "exact"), (10_000, "ivfflat"), (250_000, "ivfflat")],
)
def test_auto_picks_exact_until_an_index_would_actually_help(rows, expected):
    assert ingest.choose_index(rows, kind="auto") == expected


@pytest.mark.parametrize("kind", ["exact", "ivfflat", "hnsw"])
def test_an_explicit_index_choice_is_never_overridden(kind):
    assert ingest.choose_index(50, kind=kind) == kind
    assert ingest.choose_index(5_000_000, kind=kind) == kind


# promote is the only code that writes into the human-authored memory, so its two guards are
# the ones worth a test: it reads only from the generated area, and it writes only into memory.
def test_memory_path_rejects_an_unknown_note_type():
    with pytest.raises(ValueError):
        config.memory_path("nonsense", "x.md")


def test_memory_path_refuses_to_escape_the_memory_folder():
    with pytest.raises(ValueError):
        config.memory_path("fact", "../../rules/commit.rules.md")


def test_promote_refuses_a_source_outside_the_generated_area(tmp_path):
    stray = tmp_path / "somewhere-else.md"
    stray.write_text("# Not generated", encoding="utf-8")
    with pytest.raises(SystemExit):
        promote.promote(stray)


def test_a_relative_path_resolves_against_the_repo_not_the_shell(monkeypatch):
    monkeypatch.setenv("PMB_VAULT", "../docs")
    assert (
        config._repo_relative("PMB_VAULT", Path("/unused"))
        == (config.REPO_ROOT.parent / "docs").resolve()
    )


def test_an_absolute_path_is_left_alone(monkeypatch):
    monkeypatch.setenv("PMB_VAULT", str(Path("/tmp/elsewhere")))
    assert config._repo_relative("PMB_VAULT", Path("/unused")) == Path("/tmp/elsewhere").resolve()


def test_slug_matches_the_kebab_case_filename_rule():
    assert promote.slug("Loader uses Polars, not pandas") == "loader-uses-polars-not-pandas"
