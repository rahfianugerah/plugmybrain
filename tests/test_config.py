# The guards that matter: never write outside the generated area, never ingest a secret,
# never miscount what the folder holds.
from pathlib import Path

import pytest

from plugmybrain import bootstrap, config, export, ingest, manage


def test_namespace_is_the_lowercased_directory_name():
    assert config.namespace(Path("C:/some/Path/My-Project")) == "my-project"


def test_generated_path_stays_inside_the_folders_generated_area(tmp_path):
    path = config.generated_path(tmp_path, "code", "GRAPH_REPORT.md")
    assert path.is_relative_to((tmp_path / config.GENERATED).resolve())


def test_generated_path_refuses_to_escape(tmp_path):
    # The one that matters: `memory/` is human-authored, and a rebuild must not reach it.
    with pytest.raises(ValueError):
        config.generated_path(tmp_path, "..", "memory", "stolen.md")


@pytest.mark.parametrize(
    "name",
    [".env", ".env.local", "id_rsa.pem", "server.key", "credentials.json", "env-vars.yaml"],
)
def test_secret_filenames_are_excluded(name):
    assert config.is_excluded(Path("/project") / name)


@pytest.mark.parametrize("directory", ["keys", ".venv", "node_modules", ".git"])
def test_secret_directories_are_excluded(directory):
    assert config.is_excluded(Path("/project") / directory / "notes.md")


def test_the_generated_area_is_never_digested_back_into_itself():
    assert config.is_excluded(Path("/project") / config.GENERATED / "kg" / "node.md")


def test_ordinary_documents_are_not_excluded():
    assert not config.is_excluded(Path("/project/docs/commit.rules.md"))


def test_collect_documents_takes_markdown_and_reports_the_secrets_it_refused(tmp_path):
    (tmp_path / "keep.md").write_text("hello", encoding="utf-8")
    (tmp_path / "ignore.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=x", encoding="utf-8")
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "leak.md").write_text("secret", encoding="utf-8")

    included, skipped = config.collect_documents(tmp_path)

    # Source is Graphify's job, so .py is neither digested nor reported as a blocked secret.
    assert [p.name for p in included] == ["keep.md"]
    assert {p.name for p in skipped} == {".env", "leak.md"}


def test_the_counts_list_reports_separate_human_from_generated(tmp_path):
    (tmp_path / "README.md").write_text("#", encoding="utf-8")
    (tmp_path / config.HUMAN).mkdir()
    (tmp_path / config.HUMAN / "a-decision.md").write_text("#", encoding="utf-8")
    (tmp_path / config.GENERATED / "kg").mkdir(parents=True)
    (tmp_path / config.GENERATED / "kg" / "node.md").write_text("#", encoding="utf-8")

    markdown, skipped, human, generated = manage._on_disk(tmp_path)

    # The generated note is counted, but never as something to digest: re-digesting the model's
    # own output is how a graph starts citing itself.
    assert (markdown, human, generated) == (2, 1, 1)
    assert skipped == 0


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


def test_slug_is_stable_so_a_re_digest_overwrites_rather_than_duplicates():
    assert export.slug("Loader uses Polars, not pandas") == "loader-uses-polars-not-pandas"


def test_reset_leaves_the_hand_written_readme_in_graph(tmp_path):
    """graph/ holds a committed README explaining the folder; only its subfolders are ours."""
    generated = tmp_path / config.GENERATED
    (generated / "kg").mkdir(parents=True)
    (generated / "kg" / "node.md").write_text("#", encoding="utf-8")
    (generated / "README.md").write_text("# Graph", encoding="utf-8")

    markdown, _, _, written = manage._on_disk(tmp_path)
    # The README is generated-area markdown but not machine-written, so it is neither digested
    # nor counted as something a digest would rebuild.
    assert (markdown, written) == (0, 1)


def test_a_root_digests_its_brain_before_anything_else(tmp_path):
    """Everything else is read against the rules, so a half-finished run still leaves a brain."""
    for name in ("zeta-service", "the-rules", "alpha-service"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "README.md").write_text("#", encoding="utf-8")
    (tmp_path / "empty").mkdir()
    bootstrap.init(tmp_path / "the-rules", "brain", wire=False)

    assert [p.name for p in bootstrap.children(tmp_path)] == [
        "the-rules",
        "alpha-service",
        "zeta-service",
    ]


def test_a_folder_will_not_silently_change_role(tmp_path):
    bootstrap.init(tmp_path, "brain", wire=False)
    assert bootstrap.role_of(tmp_path) == "brain"
    with pytest.raises(SystemExit):
        bootstrap.init(tmp_path, "root", wire=False)


def test_init_scaffolds_a_brain_without_overwriting_what_is_there(tmp_path):
    (tmp_path / config.HUMAN).mkdir()
    (tmp_path / config.HUMAN / "README.md").write_text("mine", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

    bootstrap.init(tmp_path, "brain", wire=False)

    assert (tmp_path / config.HUMAN / "README.md").read_text(encoding="utf-8") == "mine"
    for note_type in bootstrap.NOTE_TYPES:
        assert (tmp_path / config.HUMAN / note_type).is_dir()
    ignored = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in ignored and "graph/kg/" in ignored
