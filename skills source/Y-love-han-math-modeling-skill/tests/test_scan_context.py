"""N04: unbound-number scanning classifies context instead of false-positiving."""

from __future__ import annotations

from scripts.mmflow_core.bindings import scan_unbound_numbers


def _tokens(source: str) -> list[str]:
    return [hit["token"] for hit in scan_unbound_numbers(source)]


def test_dates_and_calendar_years_are_not_flagged():
    source = (
        "\\begin{document}\n"
        "赛题发布于2026年8月5日，截止于2026年。\n"
        "\\end{document}\n"
    )
    assert _tokens(source) == []


def test_structural_counters_are_not_flagged():
    source = (
        "\\begin{document}\n"
        "第3节给出结果，图(2)展示，表(1)汇总。\n"
        "\\end{document}\n"
    )
    assert _tokens(source) == []


def test_measurements_with_units_are_flagged():
    source = (
        "\\begin{document}\n"
        "样本量为100个样本，耗时120秒，距离3.5公里。\n"
        "\\end{document}\n"
    )
    tokens = _tokens(source)
    assert "100" in tokens
    assert "120" in tokens
    assert "3.5" in tokens


def test_plain_integers_without_units_are_structural():
    source = (
        "\\begin{document}\n"
        "第1问、第2问共两个问题。\n"
        "\\end{document}\n"
    )
    assert _tokens(source) == []


def test_scientific_notation_flagged():
    source = (
        "\\begin{document}\n"
        "误差为1.5e-3。\n"
        "\\end{document}\n"
    )
    assert "1.5e-3" in _tokens(source)
