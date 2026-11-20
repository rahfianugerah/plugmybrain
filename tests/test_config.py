# The guards that matter: never write outside the generated area, never ingest a secret,
# never read outside the workspace, never mix two brains or two embedding models.
from pathlib import Path

import pytest

from plugmybrain import bootstrap, cli, config, ingest, manage, retrieve


def test_namespace_is_the_lowercased_directory_name():
    assert config.namespace(Path("C:/some/Path/My-Project")) == "my-project"


def test_the_workspace_itself_is_named_after_the_host_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE", tmp_path)
    monkeypatch.setenv("PMB_WORKSPACE", "C:/Users/me/Projects")
    assert config.namespace(tmp_path) == "projects"


def test_generated_path_lands_in_the_vault_under_the_brains_name():
    path = config.generated_path("code", "docs-standard", "GRAPH_REPORT.md")
    assert path.is_relative_to((config.DOCS / config.GENERATED / "code").resolve())
    assert path.name == "GRAPH_REPORT.md"


def test_generated_path_refuses_to_escape():
    # memory/ sits in the same vault, written by hand
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

    # Nor reported as a refused secret
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

    # Source is Graphify's job, so .py is neither digested nor reported
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

    assert (markdown, human, generated, skipped) == (2, 1, 1, 0)


def test_dimension_guard_matches_the_pgvector_index_ceiling():
    assert config.MAX_INDEXABLE_DIMENSIONS == 2000


# Below the threshold IVFFlat gets one list, a sequential scan with overhead
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


def test_a_root_digests_its_brain_before_anything_else(tmp_path):
    for name in ("zeta-service", "the-rules", "alpha-service"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "README.md").write_text("#", encoding="utf-8")
    (tmp_path / "empty").mkdir()
    (tmp_path / "the-rules" / config.MARKER).write_text("brain\n", encoding="utf-8")

    assert config.role_of(tmp_path / "the-rules") == "brain"
    assert [p.name for p in config.children(tmp_path)] == [
        "the-rules",
        "alpha-service",
        "zeta-service",
    ]


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "work" / "billing").mkdir(parents=True)
    return tmp_path


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("C:\\Users\\me\\Projects\\docs", "docs"),
        ("C:/Users/me/Projects/work/billing/", "work/billing"),
        ("c:\\users\\me\\projects\\docs", "docs"),
        ("/c/Users/me/Projects/work/billing", "work/billing"),
        ("work/billing", "work/billing"),
        ("C:/Users/me/Projects", ""),
    ],
)
def test_a_host_path_maps_into_the_workspace(workspace, given, expected):
    resolved = config.resolve_folder(given, host_root="C:/Users/me/Projects", mount=workspace)
    assert resolved == (workspace / expected).resolve()


def test_a_path_already_inside_the_mount_is_kept(workspace):
    inside = (workspace / "docs").as_posix()
    assert config.resolve_folder(inside, host_root="C:/x", mount=workspace) == workspace / "docs"


@pytest.mark.parametrize(
    "given",
    ["C:/Users/me/Elsewhere/docs", "/home/me/docs", "../outside", "docs/../../outside", "missing"],
)
def test_nothing_outside_the_workspace_is_reachable(workspace, given):
    with pytest.raises(ValueError):
        config.resolve_folder(given, host_root="C:/Users/me/Projects", mount=workspace)


@pytest.fixture
def no_dotenv(tmp_path, monkeypatch):
    # configure() would otherwise load this checkout's real .env
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    for key, value in {
        "DB_HOST": "db",
        "DB_NAME": "pmb",
        "DB_USERNAME": "pmb",
        "DB_PASSWORD": "placeholder",
        "EMBEDDING_DIMENSIONS": "1024",
    }.items():
        monkeypatch.setenv(key, value)
    for key in ("EMBEDDING_API_KEY", "EMBEDDING_ENDPOINT"):
        monkeypatch.delenv(key, raising=False)


def test_ollama_needs_no_key_and_finds_the_host(no_dotenv, monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_MODEL", "bge-m3")
    config.configure()
    assert config.os.environ["EMBEDDING_ENDPOINT"] == config.OLLAMA_ENDPOINT


def test_an_embedding_api_without_a_key_refuses_to_start(no_dotenv, monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("EMBEDDING_MODEL", "voyage/voyage-3.5")
    with pytest.raises(SystemExit, match="EMBEDDING_API_KEY"):
        config.configure()


def test_the_embedding_signature_changes_with_the_model(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_MODEL", "bge-m3")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1024")
    local = config.embedding_signature()
    monkeypatch.setenv("EMBEDDING_PROVIDER", "voyage")
    assert config.embedding_signature() != local


def test_a_chunk_belongs_to_a_brain_by_id_not_by_file_name():
    # Two brains both holding a README.md must not answer for each other
    ids, titles = {"id-in-docs"}, {"README"}
    assert retrieve.belongs({"document_id": "id-in-docs", "document_name": "README"}, ids, titles)
    assert not retrieve.belongs(
        {"document_id": "id-in-standard", "document_name": "README"}, ids, titles
    )


def test_setup_installs_every_command_and_drops_the_retired_ones(tmp_path):
    home = tmp_path / "home"
    old = home / ".claude" / "commands"
    old.mkdir(parents=True)
    for name in ("pmb.md", "pmb-note.md", "my-own-command.md"):
        (old / name).write_text("#", encoding="utf-8")

    report = bootstrap.setup(home=home, wire=False)

    shipped = {path.name for path in bootstrap.COMMANDS.glob("pmb*.md")}
    for agent in (home / ".claude" / "commands", home / ".codex" / "prompts"):
        assert shipped <= {path.name for path in agent.iterdir()}
    # Only the pmb namespace is cleaned, never a command somebody wrote
    assert {path.name for path in report.removed} == {"pmb.md", "pmb-note.md"}
    assert (old / "my-own-command.md").exists()


def test_the_vault_scaffold_never_overwrites(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / config.GENERATED).mkdir(parents=True)
    (vault / config.GENERATED / "README.md").write_text("mine", encoding="utf-8")
    (vault / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    monkeypatch.setattr(config, "DOCS", vault)

    cli.ensure_vault()
    cli.ensure_vault()

    assert (vault / config.GENERATED / "README.md").read_text(encoding="utf-8") == "mine"
    ignored = (vault / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in ignored and ignored.count("graph/code/") == 1
