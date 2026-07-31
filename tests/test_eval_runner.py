"""Tests for the eval runner — execution match, scoring, and the LLM judge."""

from __future__ import annotations

from src.eval.golden import GoldenQuestion
from src.eval.runner import execution_match, judge_answer, run_eval

# ── execution_match ─────────────────────────────────────────────────────────────

def test_execution_match_identical_rows() -> None:
    assert execution_match([{"x": 1}], [{"x": 1}])


def test_execution_match_ignores_row_order() -> None:
    a = [{"d": "2026-07-01"}, {"d": "2026-07-02"}]
    b = [{"d": "2026-07-02"}, {"d": "2026-07-01"}]
    assert execution_match(a, b)


def test_execution_match_ignores_column_alias_and_float_noise() -> None:
    # different alias, and 34.700001 vs 34.70 round equal
    assert execution_match([{"pic_max_mw": 34.700001}], [{"f0_": 34.70}])


def test_execution_match_detects_difference() -> None:
    assert not execution_match([{"x": 1}], [{"x": 2}])


# ── run_eval ─────────────────────────────────────────────────────────────────────

class _FakeAgent:
    """Returns a canned {answer, route, sql} per question text."""

    def __init__(self, sql_by_question: dict[str, str | None]) -> None:
        self._sql = sql_by_question

    def answer(self, question: str) -> dict:
        return {"answer": "…", "route": "sql", "sql": self._sql.get(question)}


def _fake_run_query_factory(rows_by_sql: dict[str, list[dict]]):
    def _run(sql: str, client=None):
        for needle, rows in rows_by_sql.items():
            if needle in sql:
                return rows
        return []
    return _run


def test_run_eval_scores_pass_and_fail() -> None:
    questions = [
        GoldenQuestion(id="q_ok", question="Qok", table="t", sql="SELECT a FROM consommation_journaliere"),
        GoldenQuestion(id="q_ko", question="Qko", table="t", sql="SELECT b FROM consommation_journaliere"),
    ]
    agent = _FakeAgent({"Qok": "SELECT a AS x FROM consommation_journaliere",
                        "Qko": "SELECT wrong FROM consommation_journaliere"})
    run_query_fn = _fake_run_query_factory({
        "SELECT a": [{"v": 10}],       # reference for q_ok
        "AS x": [{"v": 10}],           # agent q_ok -> match
        "SELECT b": [{"v": 20}],       # reference for q_ko
        "wrong": [{"v": 99}],          # agent q_ko -> mismatch
    })
    report = run_eval(agent, questions=questions, run_query_fn=run_query_fn)
    assert report.total == 2
    assert report.n_passed == 1
    assert report.pass_rate == 0.5
    by_id = {r.id: r for r in report.results}
    assert by_id["q_ok"].exec_match
    assert not by_id["q_ko"].exec_match


def test_run_eval_handles_missing_agent_sql() -> None:
    questions = [GoldenQuestion(id="q", question="Q", table="t", sql="SELECT 1 FROM t")]
    agent = _FakeAgent({"Q": None})
    report = run_eval(agent, questions=questions, run_query_fn=_fake_run_query_factory({"SELECT 1": [{"x": 1}]}))
    assert report.n_passed == 0
    assert "no SQL" in report.results[0].error


def test_run_eval_survives_query_error() -> None:
    questions = [GoldenQuestion(id="q", question="Q", table="t", sql="SELECT 1 FROM t")]
    agent = _FakeAgent({"Q": "SELECT boom FROM t"})

    def _boom(sql: str, client=None):
        raise RuntimeError("bad query")

    report = run_eval(agent, questions=questions, run_query_fn=_boom)
    assert report.n_passed == 0
    assert "RuntimeError" in report.results[0].error


# ── judge_answer ─────────────────────────────────────────────────────────────────

class _FakeJudge:
    def __init__(self, verdict: str) -> None:
        self._verdict = verdict

    def invoke(self, _prompt: str):
        return type("Msg", (), {"content": self._verdict})()


def test_judge_answer_yes() -> None:
    assert judge_answer(_FakeJudge("OUI, c'est correct"), "q", "a", "ref")


def test_judge_answer_no() -> None:
    assert not judge_answer(_FakeJudge("NON"), "q", "a", "ref")
