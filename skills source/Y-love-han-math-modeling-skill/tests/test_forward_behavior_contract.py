"""M14: forward behavior contract.

The audit requires true forward tests with a fresh, isolated agent that reads
only the SKILL.md and the task files.  This environment has no independent
agent runtime, so per the audit's own rule the agent-level forward test is
explicitly DISCLOSED AS NOT EXECUTED rather than faked with fixture hashes.

What is executed here is the self-containedness contract: a fresh process
with no conversation history must be able to derive, from SKILL.md alone,
the exact CLI commands the state machine will accept at every stage.
"""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from helpers import make_runtime

from scripts.mmflow import build_parser
from scripts.mmflow_core.project import next_stage

SKILL_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def test_skill_is_self_contained_fresh_process(tmp_path):
    """A fresh Python process can load the skill and derive the next command."""
    probe = (
        "import sys\n"
        "sys.path.insert(0, r'%s')\n"
        "sys.path.insert(0, r'%s/scripts')\n"
        "from scripts.mmflow import build_parser\n"
        "parser = build_parser()\n"
        "args = parser.parse_args(['next', '--project', r'%s'])\n"
        "from scripts.mmflow import dispatch\n"
        "print('OK')\n"
    ) % (str(SKILL_ROOT), str(SKILL_ROOT), str(tmp_path))
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_skill_routes_every_stage_to_a_real_command():
    parser = build_parser()
    cli_text = open(SKILL_ROOT / "scripts/mmflow.py", encoding="utf-8").read()
    commands = {
        match.group(1)
        for match in re.finditer(r'add_parser\(\s*"([^"]+)"', cli_text)
    }
    for match in re.finditer(r'for name in \((\"[^\"]+\"(?:, )*)+\s*\)\s*:', cli_text):
        for name in re.findall(r"\"([^\"]+)\"", match.group(0)):
            commands.add(name)
    skill_text = (SKILL_ROOT / "SKILL.md").read_text("utf-8")
    for stage in [f"P{i}" for i in range(12)]:
        assert stage in skill_text
    assert "gate" in skill_text
    assert "invalidate" in commands
    assert "release-status" in commands
    assert "scan-privacy" in commands
    assert "revise-entity" not in commands


def test_fresh_project_next_command_is_executable(tmp_path):
    runtime = make_runtime(tmp_path)
    action = next_stage(runtime)
    parser = build_parser()
    tokens = action["next_command"].split()
    namespace = parser.parse_args(["begin", "--project", str(tmp_path), tokens[-1]])
    assert namespace.stage == "P0"


@pytest.mark.skip(
    reason=(
        "M14 DISCLOSURE: no independent fresh-agent runtime is available in "
        "this environment, so a true forward agent test (a new AI reading "
        "only SKILL.md and the task files) was NOT EXECUTED. Per the audit, "
        "this is disclosed explicitly rather than substituted with fixture "
        "hashes. When an agent runtime is granted, run the five scenario "
        "tasks (time-series, constrained optimization, private-data block, "
        "PDE/simulation, no-data open problem) against this skill and verify "
        "state, evidence chains, BLOCKED behavior, claim boundaries, "
        "reproducibility and delivery without leaking expected answers."
    )
)
def test_true_forward_agent_scenarios():  # pragma: no cover - disclosed skip
    raise AssertionError("must not run: forward agent scenarios not executed")
