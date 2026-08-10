# The validation harness: does retrieval return the right sources, and how slow is the warm path.
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from pathlib import Path

from plugmybrain import config, retrieve

QUESTIONS = config.REPO_ROOT / "questions.yaml"


@dataclass
class Answer:
    question: str
    expected: list[str]
    found: list[str]
    seconds: float
    multihop: bool

    @property
    def hit(self) -> bool:
        return all(name in self.found for name in self.expected)


@dataclass
class EvalReport:
    answers: list[Answer]

    @property
    def score(self) -> str:
        return f"{sum(a.hit for a in self.answers)}/{len(self.answers)}"

    @property
    def p50(self) -> float:
        return statistics.median(a.seconds for a in self.answers)

    @property
    def p95(self) -> float:
        ordered = sorted(a.seconds for a in self.answers)
        return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]


async def run(dataset: str = config.CURATED_DATASET, path: Path = QUESTIONS) -> EvalReport:
    """Score every question and time the warm path.

    The first query is thrown away, because it pays for connection setup and the model's cold
    cache and would otherwise dominate p50 on a ten-question set.
    """
    import yaml

    if not path.is_file():
        raise SystemExit(f"no question set at {path}")
    questions = yaml.safe_load(path.read_text(encoding="utf-8")) or []

    await retrieve.search("warmup", dataset=dataset)

    answers: list[Answer] = []
    for item in questions:
        started = time.perf_counter()
        results = await retrieve.search(item["question"], dataset=dataset)
        elapsed = time.perf_counter() - started
        answers.append(
            Answer(
                question=item["question"],
                expected=list(item.get("expect", [])),
                found=retrieve.sources(results),
                seconds=elapsed,
                multihop=bool(item.get("multihop", False)),
            )
        )
    return EvalReport(answers=answers)
