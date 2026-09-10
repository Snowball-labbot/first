from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .canonical import (
    atomic_write_bytes,
    atomic_write_json,
    normalize_relative_posix,
    resolve_within,
    sha256_file,
)
from .errors import ConfigError, IntegrityError
from .registry import Registry


ARG_COUNTS = {
    "MMResult": 1,
    "MMResultWithUnit": 1,
    "MMClaim": 2,
    "MMGiven": 2,
    "MMCitedValue": 2,
    "MMFormulaConstant": 2,
    "MMRuleValue": 2,
}


@dataclass(frozen=True)
class Binding:
    macro: str
    arguments: tuple[str, ...]
    start: int
    end: int


def _mask_comments(source: str) -> str:
    output: list[str] = []
    for line in source.splitlines(keepends=True):
        masked = list(line)
        for index, character in enumerate(line):
            if character != "%":
                continue
            preceding = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                preceding += 1
                cursor -= 1
            if preceding % 2 == 0:
                for position in range(index, len(masked)):
                    if masked[position] not in "\r\n":
                        masked[position] = " "
                break
        output.append("".join(masked))
    return "".join(output)


def _parse_braced(source: str, position: int) -> tuple[str, int]:
    while position < len(source) and source[position].isspace():
        position += 1
    if position >= len(source) or source[position] != "{":
        raise ConfigError("binding macro argument must use braces")
    depth = 1
    cursor = position + 1
    escaped = False
    while cursor < len(source):
        character = source[cursor]
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[position + 1 : cursor], cursor + 1
        cursor += 1
    raise ConfigError("unclosed binding macro argument")


def parse_bindings(source: str) -> list[Binding]:
    masked = _mask_comments(source)
    declaration_ranges = [
        (match.start(), match.end())
        for match in re.finditer(
            r"\\(?:newcommand|renewcommand|providecommand)\*?\s*"
            r"\{\s*\\(?:"
            + "|".join(sorted(ARG_COUNTS, key=len, reverse=True))
            + r")\s*\}",
            masked,
        )
    ]
    pattern = re.compile(
        r"\\(" + "|".join(sorted(ARG_COUNTS, key=len, reverse=True)) + r")\b"
    )
    bindings: list[Binding] = []
    consumed_until = -1
    for match in pattern.finditer(masked):
        if match.start() < consumed_until:
            continue
        if any(start <= match.start() < end for start, end in declaration_ranges):
            continue
        macro = match.group(1)
        position = match.end()
        arguments: list[str] = []
        for _ in range(ARG_COUNTS[macro]):
            argument, position = _parse_braced(source, position)
            arguments.append(argument)
        consumed_until = position
        bindings.append(
            Binding(macro, tuple(arguments), match.start(), position)
        )
    return bindings


def _rules_requirement_value(
    registry: Registry, requirement_id: str, field: str
) -> str:
    """Resolve a structured competition rule value by requirement ID.

    ``MMRuleValue`` binds the official rule snapshot, not a citation: the
    requirement must exist in the current ``competition_rules`` evidence and
    the field pointer must resolve to a scalar value inside it.
    """
    candidates = [
        record["payload"]
        for record in registry.iter_latest("evidence")
        if record["payload"].get("status") == "VALID"
        and record["payload"].get("evidence_type") == "competition_rules"
    ]
    if len(candidates) != 1:
        raise IntegrityError("MMRuleValue requires exactly one current competition_rules evidence")
    content = candidates[0].get("content")
    requirements = content.get("requirements") if isinstance(content, dict) else None
    if not isinstance(requirements, list):
        raise IntegrityError("competition_rules evidence has no structured requirements")
    match = None
    for requirement in requirements:
        if isinstance(requirement, dict) and requirement.get("requirement_id") == requirement_id:
            match = requirement
            break
    if match is None:
        raise IntegrityError(f"MMRuleValue references unknown requirement: {requirement_id}")
    if not isinstance(field, str) or not field:
        raise IntegrityError("MMRuleValue requires a non-empty field pointer")
    current: Any = match
    pointer = field if field.startswith("/") else "/" + field.replace(".", "/")
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise IntegrityError(
                    f"MMRuleValue field {field} is missing from requirement {requirement_id}"
                )
            current = current[token]
        elif isinstance(current, list):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as error:
                raise IntegrityError("MMRuleValue field traverses an invalid list index") from error
        else:
            raise IntegrityError("MMRuleValue field traverses a scalar")
    if isinstance(current, (dict, list)) or current is None:
        raise IntegrityError("MMRuleValue must resolve to a scalar rule value")
    return str(current)


def _json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ConfigError("JSON pointer must start with /")
    current = document
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as error:
                raise IntegrityError("JSON pointer list index is invalid") from error
        elif isinstance(current, dict):
            if token not in current:
                raise IntegrityError("JSON pointer object key is missing")
            current = current[token]
        else:
            raise IntegrityError("JSON pointer traverses a scalar")
    return current


def verify_result_source(
    project_root: Path | str, registry: Registry, result_id: str
) -> bool:
    root = Path(project_root).resolve()
    result = registry.latest("result", result_id)["payload"]
    if result["status"] != "VALID":
        raise IntegrityError("result is not valid")
    artifact = registry.latest("artifact", result["artifact_id"])["payload"]
    if artifact["status"] != "VALID" or artifact["artifact_class"] != "production":
        raise IntegrityError("result source is not a valid production artifact")
    if artifact.get("execution_id") != result["execution_id"]:
        raise IntegrityError("result and artifact execution differ")
    execution = registry.latest("execution", result["execution_id"])["payload"]
    if execution["status"] != "VALID" or execution["exit_code"] != 0:
        raise IntegrityError("result execution is invalid")
    path = resolve_within(root, root / artifact["relative_path"], must_exist=True)
    if path.is_symlink() or sha256_file(path) != artifact["sha256"]:
        raise IntegrityError("result source artifact changed")
    locator = result["source_locator"]
    if locator.get("format") != "json_pointer" or not isinstance(
        locator.get("pointer"), str
    ):
        raise ConfigError("result binding requires a JSON pointer")
    try:
        document = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise IntegrityError("cannot parse structured result source") from error
    if document.get("schema") != "mmflow-result-contract/v1":
        raise IntegrityError("result artifact has wrong schema")
    source = _json_pointer(document, locator["pointer"])
    if not isinstance(source, dict):
        raise IntegrityError("result pointer must resolve to an object")
    for field in (
        "metric",
        "unit",
        "direction",
        "scenario",
        "dataset_split_id",
        "sample_size",
    ):
        if source.get(field) != result[field]:
            raise IntegrityError(f"result semantic mismatch: {field}")
    try:
        source_value = Decimal(str(source.get("value")))
        result_value = Decimal(str(result["value"]))
    except InvalidOperation as error:
        raise IntegrityError("result value is not decimal-compatible") from error
    if not source_value.is_finite() or source_value != result_value:
        raise IntegrityError("result numeric value mismatch")
    return True


def _latex_escape_unit(unit: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9%/._^ -]+", unit):
        raise ConfigError("unit contains unsupported LaTeX characters")
    return unit.replace("%", r"\%").replace(" ", r"\,")


def _decimal_token(value: Any) -> str:
    try:
        decimal = Decimal(str(value))
    except InvalidOperation as error:
        raise IntegrityError(f"non-decimal display value: {value}") from error
    if not decimal.is_finite():
        raise IntegrityError("display value must be finite")
    return str(decimal.normalize()) if decimal != 0 else "0"


def _numeric_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in re.finditer(
        r"(?<![A-Za-z0-9_])[-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?%?", text
    ):
        tokens.add(_decimal_token(match.group(0).rstrip("%")))
    return tokens


def _validate_claim_numbers(registry: Registry, claim: dict[str, Any]) -> None:
    statement_numbers = _numeric_tokens(claim["statement"])
    if not statement_numbers:
        return
    supported_numbers: set[str] = set()
    for support_id in claim.get("supports", []):
        support = registry.find_entity(support_id)
        kind = support["entity_kind"]
        payload = support["payload"]
        if payload.get("status") != "VALID":
            raise IntegrityError(f"claim support is not valid: {support_id}")
        if kind == "result":
            supported_numbers.add(_decimal_token(payload["display"]["rendered"]))
            uncertainty = payload.get("uncertainty") or {}
            for key in ("lower", "upper"):
                if key in uncertainty:
                    supported_numbers.add(_decimal_token(uncertainty[key]))
        elif kind == "formula":
            supported_numbers.update(
                _decimal_token(value) for value in payload.get("display_values", [])
            )
        elif kind in {"citation", "evidence"} and payload.get("display_value") is not None:
            supported_numbers.add(_decimal_token(payload["display_value"]))
    if not statement_numbers.issubset(supported_numbers):
        raise IntegrityError(
            "claim contains unbound numeric literals: "
            + str(sorted(statement_numbers - supported_numbers))
        )


def _render_binding(
    binding: Binding, registry: Registry, project_root: Path
) -> tuple[str, str]:
    entity_id = binding.arguments[0].strip()
    if binding.macro in {"MMResult", "MMResultWithUnit"}:
        verify_result_source(project_root, registry, entity_id)
        result = registry.latest("result", entity_id)["payload"]
        rendered = result["display"]["rendered"]
        if binding.macro == "MMResultWithUnit":
            rendered += r"\,\mathrm{" + _latex_escape_unit(result["unit"]) + "}"
        return rendered, entity_id
    if binding.macro == "MMClaim":
        claim = registry.latest("claim", entity_id)["payload"]
        if claim["status"] != "VALID" or claim["strength"] in {
            "unsupported",
            "hypothesis",
            "exploratory",
        }:
            raise IntegrityError("claim strength is not eligible for final manuscript")
        _validate_claim_numbers(registry, claim)
        manuscript_text = binding.arguments[1].strip()
        if manuscript_text != claim["statement"].strip():
            raise IntegrityError("manuscript claim text differs from Claim Registry")
        return manuscript_text, entity_id
    if binding.macro == "MMGiven":
        payload = registry.latest("evidence", entity_id)["payload"]
        expected = str(payload.get("display_value", ""))
    elif binding.macro == "MMCitedValue":
        payload = registry.latest("citation", entity_id)["payload"]
        expected = str(payload.get("display_value", ""))
    elif binding.macro == "MMRuleValue":
        expected = _rules_requirement_value(
            registry, binding.arguments[0], binding.arguments[1]
        )
    elif binding.macro == "MMFormulaConstant":
        payload = registry.latest("formula", entity_id)["payload"]
        values = [str(value) for value in payload.get("display_values", [])]
        if binding.arguments[1] not in values:
            raise IntegrityError("formula display value is not registered")
        return binding.arguments[1], entity_id
    else:
        raise ConfigError(f"unknown binding macro: {binding.macro}")
    if payload.get("status") != "VALID":
        raise IntegrityError(f"binding entity is not valid: {entity_id}")
    if not expected or binding.arguments[1] != expected:
        raise IntegrityError(f"display value differs from Registry for {entity_id}")
    return binding.arguments[1], entity_id


def render_latex_bindings(
    source: str,
    registry: Registry,
    project_root: Path | str,
    destination: Path | str,
) -> str:
    if _INCLUDE_PATTERN.search(_mask_comments(source)):
        raise IntegrityError(
            "source contains LaTeX includes; use render_project_latex_bindings "
            "to render the complete source closure"
        )
    bindings = parse_bindings(source)
    rendered = source
    root = Path(project_root).resolve()
    manifest_bindings: list[dict[str, Any]] = []
    for binding in reversed(bindings):
        replacement, entity_id = _render_binding(binding, registry, root)
        manifest_bindings.append(
            {
                "macro": binding.macro,
                "entity_id": entity_id,
                "replacement": replacement,
                "source_start": binding.start,
                "source_end": binding.end,
            }
        )
        rendered = rendered[: binding.start] + replacement + rendered[binding.end :]
    requested = Path(destination)
    target = resolve_within(
        root,
        requested if requested.is_absolute() else root / requested,
        must_exist=False,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8", newline="\n")
    manifest = {
        "binding_manifest_version": 1,
        "binding_count": len(bindings),
        "bindings": list(reversed(manifest_bindings)),
        "rendered_path": target.name,
        "rendered_sha256": sha256_file(target),
    }
    atomic_write_json(target.with_suffix(".bindings.json"), manifest)
    return rendered


def _project_latex_closure(
    project_root: Path | str,
    source_path: Path | str,
) -> dict[str, Any]:
    """Read a complete, project-local LaTeX include closure.

    The scanner and renderer must consume the same closure.  Keeping the
    include resolution in one helper prevents the common failure mode where
    one command validates a different set of files than the command that
    produces the manuscript.
    """

    root = Path(project_root).resolve(strict=True)
    requested = Path(source_path)
    source = resolve_within(
        root,
        requested if requested.is_absolute() else root / requested,
        must_exist=True,
    )
    if not source.is_file():
        raise IntegrityError(f"LaTeX source is not a regular file: {source}")

    records: list[dict[str, Any]] = []
    visiting: list[str] = []
    visited: dict[str, str] = {}

    def read_source(path: Path) -> tuple[Path, str, str]:
        resolved = resolve_within(root, path, must_exist=True)
        if not resolved.is_file():
            raise IntegrityError(f"LaTeX source is not a regular file: {resolved}")
        relative = normalize_relative_posix(
            resolved.relative_to(root).as_posix(), field="LaTeX source path"
        )
        try:
            content = resolved.read_text("utf-8")
        except (OSError, UnicodeError) as error:
            raise IntegrityError(f"cannot read LaTeX source: {relative}") from error
        return resolved, relative, content

    def include_target(parent: Path, raw: str) -> tuple[Path, str]:
        name = _include_name(raw)
        resolved = resolve_within(root, parent.parent / Path(name), must_exist=True)
        if not resolved.is_file():
            raise IntegrityError(f"LaTeX include source is not a regular file: {resolved}")
        relative = normalize_relative_posix(
            resolved.relative_to(root).as_posix(), field="LaTeX include path"
        )
        return resolved, relative

    def visit(path: Path) -> None:
        resolved, relative, content = read_source(path)
        key = relative.casefold()
        if key in visiting:
            cycle = " -> ".join([*visiting, key])
            raise IntegrityError(f"LaTeX include cycle detected: {cycle}")
        previous = visited.get(key)
        if previous is not None:
            if previous != relative:
                raise IntegrityError(
                    "LaTeX source paths collide after case folding: "
                    f"{previous} / {relative}"
                )
            return

        visiting.append(key)
        masked = _mask_comments(content)
        includes: list[dict[str, Any]] = []
        for match in _INCLUDE_PATTERN.finditer(masked):
            target, target_relative = include_target(resolved, match.group(1))
            includes.append(
                {
                    "start": match.start(1),
                    "end": match.end(1),
                    "target_path": target_relative,
                }
            )
            visit(target)
        visiting.pop()
        visited[key] = relative
        records.append(
            {
                "path": relative,
                "content": content,
                "sha256": sha256_file(resolved),
                "includes": includes,
            }
        )

    visit(source)
    # ``visit`` appends children before their parent.  Rendering and manifests
    # are easier to audit when the root is first and the rest follows DFS order.
    records.reverse()
    return {"root_path": records[0]["path"], "sources": records}


def _rendered_source_paths(
    closure: dict[str, Any],
    destination: Path,
    project_root: Path,
) -> dict[str, Path]:
    """Return the deterministic staged path for every source in a closure."""

    records = closure["sources"]
    root_path = Path(closure["root_path"])
    result: dict[str, Path] = {root_path.as_posix().casefold(): destination}
    stage_root = destination.parent / f"{destination.stem}.sources"
    root_parent = root_path.parent
    for record in records[1:]:
        relative = Path(record["path"])
        try:
            beneath_root = relative.relative_to(root_parent)
        except ValueError as error:
            raise IntegrityError(
                "LaTeX include path is outside the root source directory"
            ) from error
        staged = stage_root / beneath_root
        key = record["path"].casefold()
        if key in result and result[key] != staged:
            raise IntegrityError("LaTeX rendered source path collision")
        result[key] = staged
    return result


def _render_project_source(
    record: dict[str, Any],
    rendered_path: Path,
    rendered_paths: dict[str, Path],
    registry: Registry,
    project_root: Path,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Render bindings and rewrite include arguments for one source file."""

    operations: list[tuple[int, int, str]] = []
    binding_records: list[dict[str, Any]] = []
    for binding in parse_bindings(record["content"]):
        replacement, entity_id = _render_binding(binding, registry, project_root)
        binding_records.append(
            {
                "source_path": record["path"],
                "source_sha256": record["sha256"],
                "macro": binding.macro,
                "entity_id": entity_id,
                "replacement": replacement,
                "source_start": binding.start,
                "source_end": binding.end,
            }
        )
        operations.append((binding.start, binding.end, replacement))

    include_records: list[dict[str, Any]] = []
    for include in record["includes"]:
        target = rendered_paths.get(include["target_path"].casefold())
        if target is None:
            raise IntegrityError(
                f"rendered LaTeX include target is missing: {include['target_path']}"
            )
        relative_target = Path(os.path.relpath(target, rendered_path.parent)).as_posix()
        if relative_target.startswith("../") or relative_target == "..":
            raise IntegrityError("rendered LaTeX include escapes its output directory")
        operations.append((include["start"], include["end"], relative_target))
        include_records.append(
            {
                "source_path": record["path"],
                "target_source_path": include["target_path"],
                "rendered_target_path": target,
                "source_start": include["start"],
                "source_end": include["end"],
                "replacement": relative_target,
            }
        )

    rendered = record["content"]
    for start, end, replacement in sorted(operations, key=lambda item: item[0], reverse=True):
        rendered = rendered[:start] + replacement + rendered[end:]
    return rendered, binding_records, include_records


def render_project_latex_bindings(
    source_path: Path | str,
    registry: Registry,
    project_root: Path | str,
    destination: Path | str,
) -> dict[str, Any]:
    """Render a LaTeX source and every recursive include into a staged closure.

    The root file remains a normal LaTeX file.  Included files are written to
    ``<destination-stem>.sources`` and include arguments are rewritten to that
    staged tree.  The version-2 manifest records both the original and rendered
    closure so P8 can verify every source, not only the root file.
    """

    root = Path(project_root).resolve(strict=True)
    requested_destination = Path(destination)
    destination_path = resolve_within(
        root,
        requested_destination
        if requested_destination.is_absolute()
        else root / requested_destination,
        must_exist=False,
    )
    closure = _project_latex_closure(root, source_path)
    rendered_paths = _rendered_source_paths(closure, destination_path, root)

    all_bindings: list[dict[str, Any]] = []
    rendered_closure: list[dict[str, Any]] = []
    include_rewrites: list[dict[str, Any]] = []
    for record in closure["sources"]:
        rendered_path = rendered_paths[record["path"].casefold()]
        rendered, bindings, includes = _render_project_source(
            record, rendered_path, rendered_paths, registry, root
        )
        rendered_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(rendered_path, rendered.encode("utf-8"))
        all_bindings.extend(bindings)
        include_rewrites.extend(
            {
                **item,
                "rendered_target_path": resolve_within(
                    root, item["rendered_target_path"], must_exist=False
                ).relative_to(root).as_posix(),
            }
            for item in includes
        )
        rendered_closure.append(
            {
                "source_path": record["path"],
                "source_sha256": record["sha256"],
                "rendered_path": rendered_path.relative_to(root).as_posix(),
                "rendered_sha256": sha256_file(rendered_path),
            }
        )

    manifest = {
        "binding_manifest_version": 2,
        "root_source_path": closure["root_path"],
        "rendered_path": destination_path.relative_to(root).as_posix(),
        "rendered_sha256": sha256_file(destination_path),
        "binding_count": len(all_bindings),
        "bindings": all_bindings,
        "source_closure": [
            {"path": item["path"], "sha256": item["sha256"]}
            for item in closure["sources"]
        ],
        "rendered_source_closure": rendered_closure,
        "include_rewrites": include_rewrites,
    }
    atomic_write_json(destination_path.with_suffix(".bindings.json"), manifest)
    return manifest


def verify_project_binding_manifest(
    project_root: Path | str,
    source_path: Path | str,
    manifest: dict[str, Any],
    registry: Registry,
    rendered_sources: dict[str, str] | None = None,
) -> bool:
    """Recompute and verify a version-2 recursive LaTeX binding manifest."""

    if not isinstance(manifest, dict) or manifest.get("binding_manifest_version") != 2:
        raise IntegrityError("project binding manifest has an unsupported version")
    root = Path(project_root).resolve(strict=True)
    closure = _project_latex_closure(root, source_path)
    declared = manifest.get("source_closure")
    observed = [
        {"path": item["path"], "sha256": item["sha256"]}
        for item in closure["sources"]
    ]
    if not isinstance(declared, list) or not source_closure_matches(observed, declared):
        raise IntegrityError("project binding source closure differs from current files")
    if manifest.get("root_source_path") != closure["root_path"]:
        raise IntegrityError("project binding root source differs from current source")
    rendered_relative = normalize_relative_posix(
        manifest.get("rendered_path"), field="rendered manuscript path"
    )
    destination = resolve_within(root, root / rendered_relative, must_exist=True)
    rendered_paths = _rendered_source_paths(closure, destination, root)
    declared_rendered = manifest.get("rendered_source_closure")
    if not isinstance(declared_rendered, list):
        raise IntegrityError("project binding manifest lacks rendered source closure")
    by_source: dict[str, dict[str, Any]] = {}
    for item in declared_rendered:
        if not isinstance(item, dict):
            raise IntegrityError("rendered source closure item is invalid")
        source_name = item.get("source_path")
        if not isinstance(source_name, str) or source_name.casefold() in by_source:
            raise IntegrityError("rendered source closure has duplicate source paths")
        expected_path = rendered_paths.get(source_name.casefold())
        if expected_path is None:
            raise IntegrityError("rendered source closure contains an unknown source")
        declared_path = normalize_relative_posix(
            item.get("rendered_path"), field="rendered source path"
        )
        if declared_path != expected_path.relative_to(root).as_posix():
            raise IntegrityError("rendered source path does not match deterministic staging")
        by_source[source_name.casefold()] = item
    if set(by_source) != {item["path"].casefold() for item in closure["sources"]}:
        raise IntegrityError("rendered source closure is incomplete")

    expected_bindings: list[dict[str, Any]] = []
    expected_rewrites: list[dict[str, Any]] = []
    for record in closure["sources"]:
        rendered_path = rendered_paths[record["path"].casefold()]
        expected, bindings, includes = _render_project_source(
            record, rendered_path, rendered_paths, registry, root
        )
        item = by_source[record["path"].casefold()]
        actual_path = resolve_within(
            root, root / item["rendered_path"], must_exist=True
        )
        if actual_path != rendered_path or not actual_path.is_file():
            raise IntegrityError("rendered source path is missing or misplaced")
        actual = actual_path.read_text("utf-8")
        if rendered_sources is not None:
            supplied = rendered_sources.get(record["path"])
            if supplied is not None and supplied != actual:
                raise IntegrityError("supplied rendered source differs from disk")
        if actual != expected:
            raise IntegrityError(
                f"rendered LaTeX source differs from Registry render: {record['path']}"
            )
        if item.get("source_sha256") != record["sha256"] or item.get(
            "rendered_sha256"
        ) != sha256_file(actual_path):
            raise IntegrityError("rendered source closure hash mismatch")
        if parse_bindings(actual):
            raise IntegrityError("rendered LaTeX source contains unresolved bindings")
        expected_bindings.extend(bindings)
        expected_rewrites.extend(
            {
                **include,
                "rendered_target_path": resolve_within(
                    root, include["rendered_target_path"], must_exist=False
                ).relative_to(root).as_posix(),
            }
            for include in includes
        )

    if manifest.get("binding_count") != len(expected_bindings):
        raise IntegrityError("project binding count differs from source closure")
    if manifest.get("bindings") != expected_bindings:
        raise IntegrityError("project binding mappings differ from current Registry")
    if manifest.get("include_rewrites") != expected_rewrites:
        raise IntegrityError("project include rewrites differ from current sources")
    if manifest.get("rendered_sha256") != sha256_file(destination):
        raise IntegrityError("project root rendered hash differs from manifest")
    return True


def expected_binding_render(
    source: str, registry: Registry, project_root: Path | str
) -> tuple[str, list[dict[str, Any]]]:
    bindings = parse_bindings(source)
    rendered = source
    root = Path(project_root).resolve()
    manifest_bindings: list[dict[str, Any]] = []
    for binding in reversed(bindings):
        replacement, entity_id = _render_binding(binding, registry, root)
        manifest_bindings.append(
            {
                "macro": binding.macro,
                "entity_id": entity_id,
                "replacement": replacement,
                "source_start": binding.start,
                "source_end": binding.end,
            }
        )
        rendered = rendered[: binding.start] + replacement + rendered[binding.end :]
    return rendered, list(reversed(manifest_bindings))


def verify_binding_manifest(
    source: str,
    rendered: str,
    manifest: dict[str, Any],
    registry: Registry,
    project_root: Path | str,
) -> bool:
    if not isinstance(manifest, dict) or manifest.get("binding_manifest_version") != 1:
        raise IntegrityError("binding manifest has an unsupported version")
    expected_rendered, expected_bindings = expected_binding_render(
        source, registry, project_root
    )
    if rendered != expected_rendered:
        raise IntegrityError("production manuscript differs from current Registry render")
    if manifest.get("binding_count") != len(expected_bindings):
        raise IntegrityError("binding manifest count differs from source bindings")
    if manifest.get("bindings") != expected_bindings:
        raise IntegrityError("binding manifest mappings differ from current Registry")
    rendered_sha256 = __import__("hashlib").sha256(rendered.encode("utf-8")).hexdigest()
    if manifest.get("rendered_sha256") != rendered_sha256:
        raise IntegrityError("binding manifest rendered hash differs from manuscript")
    return True


def _mask_binding_ranges(source: str) -> str:
    masked = list(_mask_comments(source))
    for binding in parse_bindings(source):
        for index in range(binding.start, binding.end):
            if masked[index] not in "\r\n":
                masked[index] = " "
    return "".join(masked)


def scan_unbound_numbers(source: str) -> list[dict[str, Any]]:
    text = _mask_binding_ranges(source)
    begin = text.find(r"\begin{document}")
    end = text.rfind(r"\end{document}")
    if begin >= 0 and end > begin:
        offset = begin + len(r"\begin{document}")
        text = text[offset:end]
    else:
        offset = 0
    text = re.sub(
        r"\\(?:ref|pageref|eqref|label|cite|autoref)\s*\{[^{}]*\}", " ", text
    )
    text = re.sub(
        r"\\(?:section|subsection|subsubsection|chapter)\*?\s*\{[^{}]*\}",
        " ",
        text,
    )
    text = re.sub(r"(?<=[A-Za-z}])_[{]?\d+[}]?", "_{}", text)
    text = re.sub(r"(?<=[A-Za-z}])\^[{]?\d+[}]?", "^{}", text)
    # N04 context classification: dates, structural counters and standalone
    # calendar years are structural text, not empirical claims.
    text = re.sub(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日", " ", text)
    text = re.sub(r"\d{1,2}\s*月\s*\d{1,2}\s*日", " ", text)
    text = re.sub(r"第\s*\d+\s*[节章式]", " ", text)
    text = re.sub(r"(?:图|表|式)\s*\(\s*\d+\s*\)", " ", text)
    text = re.sub(r"\d{4}\s*年", " ", text)
    pattern = re.compile(
        r"(?<![A-Za-z0-9_])[-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?%?"
    )
    hits: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        token = match.group(0)
        # Integers used only as symbolic coefficients are structural, not
        # empirical claims; standalone 4-digit calendar years are likewise
        # treated as structural text unless a unit makes them measurements.
        suffix = text[match.end() : match.end() + 32]
        unit_match = re.match(
            r"\s*(?:\\?\s*%|(?:samples?|observations?|km\s*/\s*h|m\s*/\s*s|"
            r"kg|g|mg|s|ms|h|days?|years?|units?|people|items?)(?![A-Za-z])|"
            r"(?:个\s*)?(?:样本|观测|单位|项目|物品)|"
            r"(?:毫秒|秒|分钟|小时|天|日|周|月|年|人|位|公里|千米|米|厘米|毫米|"
            r"千克|公斤|克|毫克)(?![\u4e00-\u9fff]))",
            suffix,
            re.IGNORECASE,
        )
        if "." not in token and "e" not in token.lower() and not unit_match:
            continue
        absolute = offset + match.start()
        hits.append(
            {
                "token": token,
                "line": source.count("\n", 0, absolute) + 1,
                "offset": absolute,
            }
        )
    return hits


_INCLUDE_PATTERN = re.compile(r"\\(?:input|include|subfile)\s*\{([^{}]+)\}")


def _include_name(raw: str) -> str:
    name = raw.strip().replace("\\", "/")
    if not name or name.startswith("/") or ".." in Path(name).parts:
        raise IntegrityError(f"unsafe LaTeX include path: {raw}")
    if not name.lower().endswith(".tex"):
        name += ".tex"
    return Path(name).as_posix()


def scan_latex_sources(
    source: str,
    included_sources: dict[str, str],
    *,
    root_name: str = "main.tex",
) -> list[dict[str, Any]]:
    """Scan a bounded LaTeX source closure and fail on missing/cyclic input."""

    normalized_sources = {
        Path(key.replace("\\", "/")).as_posix(): value
        for key, value in included_sources.items()
    }
    root = _include_name(root_name)
    normalized_sources.setdefault(root, source)
    visiting: list[str] = []
    visited: set[str] = set()
    chunks: list[tuple[str, str]] = []

    def visit(name: str) -> None:
        if name in visiting:
            cycle = " -> ".join([*visiting, name])
            raise IntegrityError(f"LaTeX include cycle detected: {cycle}")
        if name in visited:
            return
        content = normalized_sources.get(name)
        if not isinstance(content, str):
            raise IntegrityError(f"LaTeX include source is missing: {name}")
        visiting.append(name)
        chunks.append((name, content))
        for match in _INCLUDE_PATTERN.finditer(_mask_comments(content)):
            visit(_include_name(match.group(1)))
        visiting.pop()
        visited.add(name)

    visit(root)
    hits: list[dict[str, Any]] = []
    for name, content in chunks:
        hits.extend({**hit, "source_path": name} for hit in scan_unbound_numbers(content))
    return hits


def scan_project_latex_sources(
    project_root: Path | str,
    source_path: Path | str,
) -> dict[str, Any]:
    """Read and scan a bounded project-local LaTeX source closure.

    The returned ``sources`` list is a content-addressed inventory suitable
    for P8 evidence.  Include paths are resolved relative to the including
    file's directory, and every path is checked through the canonical project
    resolver before reading.
    """

    root = Path(project_root).resolve(strict=True)
    requested = Path(source_path)
    source = resolve_within(
        root,
        requested if requested.is_absolute() else root / requested,
        must_exist=True,
    )
    if not source.is_file():
        raise IntegrityError(f"LaTeX source is not a regular file: {source}")
    source_texts: dict[str, str] = {}
    source_hashes: dict[str, str] = {}
    visiting: list[str] = []
    visited: set[str] = set()
    chunks: list[tuple[str, str]] = []

    def read_source(path: Path) -> tuple[str, str]:
        resolved = resolve_within(root, path, must_exist=True)
        if not resolved.is_file():
            raise IntegrityError(f"LaTeX source is not a regular file: {resolved}")
        relative = normalize_relative_posix(
            resolved.relative_to(root).as_posix(), field="LaTeX source path"
        )
        try:
            text = resolved.read_text("utf-8")
        except (OSError, UnicodeError) as error:
            raise IntegrityError(f"cannot read LaTeX source: {relative}") from error
        return relative, text

    def include_path(parent: Path, raw: str) -> Path:
        name = _include_name(raw)
        return parent.parent / Path(name)

    def visit(path: Path) -> None:
        relative, content = read_source(path)
        if relative in visiting:
            cycle = " -> ".join([*visiting, relative])
            raise IntegrityError(f"LaTeX include cycle detected: {cycle}")
        if relative in visited:
            return
        visiting.append(relative)
        source_texts[relative] = content
        source_hashes[relative] = sha256_file(root / relative)
        chunks.append((relative, content))
        for match in _INCLUDE_PATTERN.finditer(_mask_comments(content)):
            visit(include_path(path, match.group(1)))
        visiting.pop()
        visited.add(relative)

    visit(source)
    hits: list[dict[str, Any]] = []
    for relative, content in chunks:
        hits.extend({**hit, "source_path": relative} for hit in scan_unbound_numbers(content))
    return {
        "sources": [
            {"path": relative, "sha256": source_hashes[relative]}
            for relative in sorted(source_texts)
        ],
        "hits": hits,
    }


def source_closure_matches(
    observed: list[dict[str, Any]], declared: list[dict[str, Any]]
) -> bool:
    """Compare source closure identity while leaving artifact bindings separate."""

    def project(items: list[dict[str, Any]]) -> list[tuple[Any, Any]]:
        return sorted((item.get("path"), item.get("sha256")) for item in items)

    return project(observed) == project(declared)
