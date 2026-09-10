"""Shared publication-safe plotting and sidecar helpers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable


def _require_production_input(data: dict[str, Any]) -> None:
    if data.get("artifact_class", "production") != "production":
        raise ValueError("visualization input must be production-eligible")
    for field in ("question_id", "input_artifact_ids", "input_sha256", "units", "sample_size"):
        if field not in data:
            raise ValueError(f"visualization input missing {field}")
    if not isinstance(data["input_artifact_ids"], list) or not data["input_artifact_ids"]:
        raise ValueError("input_artifact_ids must be a non-empty list")
    if not isinstance(data["sample_size"], int) or data["sample_size"] <= 0:
        raise ValueError("sample_size must be positive")


def _matplotlib():
    # MPLCONFIGDIR 必须落到系统临时目录：回退到 "." 会在进程当前目录
    # （例如 pytest 的 skill 源树 cwd）里生成 mplconfig 缓存，污染源树
    # 与交付卫生检查。
    import tempfile

    cache_root = os.environ.get("TMPDIR") or tempfile.gettempdir()
    os.environ.setdefault(
        "MPLCONFIGDIR", str(Path(cache_root) / "mmflow-mplconfig")
    )
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    # 中文竞赛标签（图题/轴标/系列名）必须可渲染：按平台给出 CJK
    # 字体回退链；axes.unicode_minus 防止负号在 CJK 字体下变豆腐块。
    cjk_chain = (
        "Microsoft YaHei, SimHei, PingFang SC, Hiragino Sans GB, "
        "Noto Sans CJK SC, Source Han Sans SC, WenQuanYi Micro Hei, sans-serif"
    )
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "font.size": 10,
            "font.sans-serif": cjk_chain.split(", "),
            "axes.unicode_minus": False,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "savefig.bbox": "tight",
        }
    )
    return plt


def _series(data: dict[str, Any]) -> tuple[list[float], list[float]]:
    x = data.get("x")
    y = data.get("y")
    if not isinstance(x, list) or not isinstance(y, list) or len(x) != len(y) or not x:
        raise ValueError("visualization input requires equal non-empty x and y lists")
    return [float(item) for item in x], [float(item) for item in y]


def save_figure(
    data: dict[str, Any],
    output_dir: Path | str,
    *,
    role: str,
    drawer: Callable[[Any, dict[str, Any]], None],
) -> dict[str, str]:
    _require_production_input(data)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    plt = _matplotlib()
    figure = plt.figure(figsize=(7.2, 4.6))
    drawer(figure, data)
    image = output / f"{role}.png"
    figure.savefig(image, dpi=300, bbox_inches="tight", pad_inches=0.1)
    plt.close(figure)
    image_hash = hashlib.sha256(image.read_bytes()).hexdigest()
    # 受控 runner 会注入 MMFLOW_EXECUTION_ID；sidecar 必须回写该 ID，
    # 否则 Registry 的图像-sidecar 同执行锁校验会拒绝登记。
    execution_id = os.environ.get("MMFLOW_EXECUTION_ID", "")
    sidecar = {
        "schema": "mmflow-figure-sidecar/v2",
        "image_sha256": image_hash,
        "execution_id": execution_id,
        "question_id": data["question_id"],
        "role": role,
        "necessity": data.get("necessity", "required"),
        "backend": "python",
        "generator_artifact_id": data.get("generator_artifact_id", f"template.visualization.{role}"),
        "input_artifact_ids": list(data["input_artifact_ids"]),
        "input_sha256": dict(data["input_sha256"]),
        "units": dict(data["units"]),
        "uncertainty_description": data.get("uncertainty_description", "not applicable"),
        "sample_size": data["sample_size"],
        "information_gain": data.get("information_gain", f"{role} exposes a question-specific structure"),
        "paper_locator": data.get("paper_locator", "unassigned"),
        "rendering_audit_id": data.get("rendering_audit_id", "pending_audit"),
        "source_result_ids": list(data.get("source_result_ids", [])),
    }
    sidecar_path = output / f"{role}.sidecar.json"
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"image_path": str(image), "sidecar_path": str(sidecar_path)}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_item(
    question_id: str,
    data_sources,
    *,
    units: dict[str, str] | None = None,
    sample_size: int | None = None,
    artifact_ids=None,
    **extra: Any,
) -> dict[str, Any]:
    """从数据文件自动构造生产图 item 的"一键出图"辅助。

    消除手工计算 input_sha256 的最后一公里：
    - ``data_sources``：artifact_id -> 本地文件路径 的映射（或路径列表，
      此时 artifact_id 取文件名 stem）；每个文件自动计算 sha256；
    - ``artifact_ids``：显式指定 input_artifact_ids 顺序（默认取映射键）；
    - ``sample_size`` 缺省时对 csv/xlsx 自动计数行数，其余类型必须显式给出。

    返回可直接作为 generate_all plan 中 ``data`` 字段（或各模块
    ``generate(data, out_dir)`` 入参）的 dict。
    """
    if isinstance(data_sources, (str, Path)):
        data_sources = [data_sources]
    sha_map: dict[str, str] = {}
    paths: list[Path] = []
    for artifact_id, raw in (data_sources.items() if isinstance(data_sources, dict) else []):
        path = Path(raw)
        if not path.is_file():
            raise ValueError(f"data source not found: {path}")
        sha_map[str(artifact_id)] = _file_sha256(path)
        paths.append(path)
    if not isinstance(data_sources, dict):
        for raw in data_sources:
            path = Path(raw)
            if not path.is_file():
                raise ValueError(f"data source not found: {path}")
            artifact_id = f"art_{path.stem}"
            sha_map[artifact_id] = _file_sha256(path)
            paths.append(path)
    ids = list(artifact_ids) if artifact_ids is not None else list(sha_map)
    missing = [i for i in ids if i not in sha_map]
    if missing:
        raise ValueError(f"artifact_ids not covered by data sources: {missing}")
    if sample_size is None:
        counted = None
        for path in paths:
            suffix = path.suffix.lower()
            if suffix == ".csv":
                import csv as _csv
                with path.open("r", encoding="utf-8-sig", errors="replace",
                               newline="") as handle:
                    counted = max(counted or 0,
                                  sum(1 for _ in _csv.reader(handle)) - 1)
            elif suffix in {".xlsx", ".xlsm"}:
                try:
                    import openpyxl
                except ImportError:
                    continue
                book = openpyxl.load_workbook(path, read_only=True)
                sheet = book.active
                counted = max(counted or 0, max((sheet.max_row or 1) - 1, 0))
                book.close()
        if counted is None or counted <= 0:
            raise ValueError("sample_size must be provided for non-tabular data")
        sample_size = int(counted)
    if sample_size is None or int(sample_size) <= 0:
        raise ValueError("sample_size must be positive")
    item: dict[str, Any] = {
        "question_id": str(question_id),
        "input_artifact_ids": ids,
        "input_sha256": sha_map,
        "units": dict(units or {}),
        "sample_size": int(sample_size),
    }
    item.update(extra)
    return item

