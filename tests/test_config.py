# The guards that matter: never write outside the generated area, never ingest a secret,
# never miscount what the folder holds.
from pathlib import Path

import pytest

from plugmybrain import bootstrap, config, ingest, manage, retrieve


def test_namespace_is_the_lowercased_directory_name():
    assert config.namespace(Path("C:/some/Path/My-Project")) == "my-project"


def test_generated_path_lands_in_the_vault_under_the_brains_name():
    path = config.generated_path("code", "docs-standard", "GRAPH_REPORT.md")
    assert path.is_relative_to((config.DOCS / config.GENERATED / "code").resolve())
    assert path.name == "GRAPH_REPORT.md"


def test_generated_path_refuses_to_escape():
    # The one that matters: `memory/` is human-authored and sits in the same vault, so a
    # rebuild that could climb out of graph/ could overwrite a note somebody wrote.
    with pytest.raises(ValueError):
        config.generated_path("code", "../../memory", "stolen.md")
    with pytest.raises(ValueError):
        config.generated_path("memory", "anything")


@pytest.mark.parametrize(
    "name",
    [".env", ".env.local", "id_rsa.pem", "server.key", "credentials.json", "env-vars.yaml"],
)
def test_secret_filenames_are_excluded(name):
    assert config.is_excluded(Path("/project") / name)


@pytest.mark.parametrize("directory", ["keys", ".venv", "node_modules", ".git"])
def test_secret_directories_are_excluded(directory):
    assert config.is_excluded(Path("/project") / directory / "notes.md")


def test_the_generated_area_is_never_digested_back_into_itself(tmp_path):
    assert config.is_excluded(Path("/project") / config.GENERATED / "code" / "report.md")

    # And it is not reported as a refused secret either. The vault holds both the notes to
    # digest and the notes a digest produced, so "skipped" would otherwise accuse the tool's
    # own output of looking like a leaked key.
    (tmp_path / config.GENERATED / "code").mkdir(parents=True)
    (tmp_path / config.GENERATED / "code" / "report.md").write_text("#", encoding="utf-8")
    (tmp_path / "real.md").write_text("#", encoding="utf-8")
    included, skipped = config.collect_documents(tmp_path)
    assert [p.name for p in included] == ["real.md"]
    assert skipped == []


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


def test_the_counts_read_generated_notes_from_the_vault(tmp_path, monkeypatch):
    project = tmp_path / "some-service"
    (project / config.HUMAN).mkdir(parents=True)
    (project / "README.md").write_text("#", encoding="utf-8")
    (project / config.HUMAN / "a-decision.md").write_text("#", encoding="utf-8")

    vault = tmp_path / "vault" / config.GENERATED / "code" / "some-service"
    vault.mkdir(parents=True)
    (vault / "GRAPH_REPORT.md").write_text("#", encoding="utf-8")
    monkeypatch.setattr(config, "DOCS", tmp_path / "vault")

    markdown, skipped, human, generated = manage._on_disk(project)

    # Two markdown in the folder, and the generated note counted from the vault rather than
    # from the folder, which is never written to.
    assert (markdown, human, generated, skipped) == (2, 1, 1, 0)


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


def test_a_root_digests_its_brain_before_anything_else(tmp_path, monkeypatch):
    """Everything else is read against the rules, so a half-finished run still leaves a brain."""
    for name in ("zeta-service", "the-rules", "alpha-service"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "README.md").write_text("#", encoding="utf-8")
    (tmp_path / "empty").mkdir()
    monkeypatch.setattr(config, "DOCS", tmp_path / "vault")
    bootstrap.init(tmp_path / "the-rules", "brain", wire=False)

    assert [p.name for p in bootstrap.children(tmp_path)] == [
        "the-rules",
        "alpha-service",
        "zeta-service",
    ]


def test_init_drops_a_command_this_project_no_longer_ships(tmp_path):
    """A command that outlives its action keeps offering it. `/pmb-note` called `pmb note`."""
    commands = tmp_path / "commands"
    commands.mkdir()
    for name in ("pmb.md", "pmb-map.md", "pmb-note.md", "my-own-command.md"):
        (commands / name).write_text("#", encoding="utf-8")

    stale = bootstrap._stale_commands(commands, {"pmb.md", "pmb-map.md"})

    # Only the `pmb` namespace, and only what `agents/` no longer holds.
    assert [path.name for path in stale] == ["pmb-note.md"]


def test_a_folder_will_not_silently_change_role(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DOCS", tmp_path / "vault")
    bootstrap.init(tmp_path, "brain", wire=False)
    assert bootstrap.role_of(tmp_path) == "brain"
    with pytest.raises(SystemExit):
        bootstrap.init(tmp_path, "root", wire=False)


def test_init_scaffolds_a_brain_without_overwriting_what_is_there(tmp_path, monkeypatch):
    brain, vault = tmp_path / "brain", tmp_path / "vault"
    (brain / config.HUMAN).mkdir(parents=True)
    (brain / config.HUMAN / "README.md").write_text("mine", encoding="utf-8")
    vault.mkdir()
    (vault / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    monkeypatch.setattr(config, "DOCS", vault)

    bootstrap.init(brain, "brain", wire=False)

    assert (brain / config.HUMAN / "README.md").read_text(encoding="utf-8") == "mine"
    for note_type in bootstrap.NOTE_TYPES:
        assert (brain / config.HUMAN / note_type).is_dir()
    # Nothing generated is written into the brain: a digested folder is only ever read.
    assert not (brain / config.GENERATED).exists()
    ignored = (vault / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in ignored and "graph/code/" in ignored


def test_a_chunk_belongs_to_a_brain_by_id_not_by_file_name():
    # Two brains both holding a README.md must not answer for each other
    ids, titles = {"id-in-docs"}, {"README"}
    assert retrieve.belongs({"document_id": "id-in-docs", "document_name": "README"}, ids, titles)
    assert not retrieve.belongs(
        {"document_id": "id-in-standard", "document_name": "README"}, ids, titles
    )
