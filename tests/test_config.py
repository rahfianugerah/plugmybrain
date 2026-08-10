# The guards that matter: never write above the generated area, never ingest a secret.
from pathlib import Path

import pytest

from brain import config


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


def test_dimension_guard_matches_the_pgvector_hnsw_ceiling():
    assert config.MAX_INDEXABLE_DIMENSIONS == 2000
