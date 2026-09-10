"""N03: macro signature contract and rule-driven MMRuleValue."""

from __future__ import annotations

import pytest

from helpers import build_through

from scripts.mmflow_core.bindings import (
    ARG_COUNTS,
    _rules_requirement_value,
    parse_bindings,
)
from scripts.mmflow_core.errors import IntegrityError


def test_macro_argument_contract():
    assert ARG_COUNTS["MMResult"] == 1
    assert ARG_COUNTS["MMResultWithUnit"] == 1
    assert ARG_COUNTS["MMClaim"] == 2
    assert ARG_COUNTS["MMGiven"] == 2
    assert ARG_COUNTS["MMCitedValue"] == 2
    assert ARG_COUNTS["MMFormulaConstant"] == 2
    assert ARG_COUNTS["MMRuleValue"] == 2


def test_parse_bindings_argument_counts():
    bindings = parse_bindings(
        "\\MMResult{res_x} \\MMRuleValue{pdf_required}{value} \\MMClaim{c_x}{text}"
    )
    macros = [binding.macro for binding in bindings]
    assert macros == ["MMResult", "MMRuleValue", "MMClaim"]
    assert bindings[0].arguments == ("res_x",)
    assert bindings[1].arguments == ("pdf_required", "value")


def test_rule_value_binds_requirement_not_citation(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    # pdf_required=false is the registered requirement.
    value = _rules_requirement_value(
        runtime.registry, "pdf_required", "value"
    )
    assert value == "False"
    scope = _rules_requirement_value(runtime.registry, "pdf_required", "scope")
    assert scope == "paper"


def test_rule_value_unknown_requirement_rejected(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    with pytest.raises(IntegrityError):
        _rules_requirement_value(runtime.registry, "no_such_rule", "value")


def test_rule_value_missing_field_rejected(tmp_path):
    runtime, _ = build_through(tmp_path, "P0")
    with pytest.raises(IntegrityError):
        _rules_requirement_value(runtime.registry, "pdf_required", "no_such_field")
