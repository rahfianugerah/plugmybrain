# The guard that matters: a regeneration must never be able to write above the generated area.
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
