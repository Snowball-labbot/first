# figures_style.py — 生产图样式与元数据剥离工具（P5/P8，production 层）
# 用途：
#   1) 提供统一的出版级 rcParams（呼应 analytics/utils.py 的 Okabe-Ito 主板，
#      但 production 层自包含、不依赖 analytics 目录）；
#   2) save_stripped()：保存 PNG 时剥离默认写入的 Software 元数据，
#      交付隐私扫描（scan-privacy）不再因 PNG Software 字段记录生成环境；
#   3) png_text_metadata()：读取 PNG tEXt/iTXt 块，供自检确认剥离结果。
# 依赖：matplotlib（可选 numpy）。通过受控 runner 执行以获得 execution 证明。
from __future__ import annotations

import struct
import zlib
from pathlib import Path

PRODUCTION_RC = {
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "savefig.bbox": "tight",
    "axes.unicode_minus": False,
    # CJK 字体回退链：中文竞赛标签在跨平台渲染不出现豆腐块
    "font.sans-serif": [
        "Microsoft YaHei", "SimHei", "PingFang SC", "Hiragino Sans GB",
        "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei",
        "sans-serif",
    ],
}

SERIES_COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#56B4E9", "#E69F00"]


def apply_production_style(plt) -> None:
    """在 import matplotlib.pyplot 之后、绘图之前调用一次。"""
    plt.rcParams.update(PRODUCTION_RC)


def save_stripped(fig, path, **savefig_kwargs) -> Path:
    """保存 PNG 并剥离 Software 等自动元数据。

    matplotlib 对 PNG 默认写入 {"Software": "matplotlib version ..."}；
    显式传入 metadata 后以调用方内容为准，空 dict 即无自定义键。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    figure_kwargs = {"dpi": 300, "bbox_inches": "tight", "pad_inches": 0.1}
    figure_kwargs.update(savefig_kwargs)
    fig.savefig(target, format="png", metadata={}, **figure_kwargs)
    return target


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_text_metadata(path) -> dict[str, str]:
    """解析 PNG 的 tEXt/iTXt/zTXt 关键字对（含 Software 字段检查）。"""
    data = Path(path).read_bytes()
    if not data.startswith(_PNG_SIGNATURE):
        raise ValueError(f"not a PNG file: {path}")
    metadata: dict[str, str] = {}
    offset = len(_PNG_SIGNATURE)
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset: offset + 4])[0]
        chunk_type = data[offset + 4: offset + 8]
        chunk_data = data[offset + 8: offset + 8 + length]
        if chunk_type == b"tEXt":
            keyword, _, value = chunk_data.partition(b"\x00")
            metadata[keyword.decode("latin-1")] = value.decode("latin-1",
                                                               errors="replace")
        elif chunk_type == b"iTXt":
            keyword, _, rest = chunk_data.partition(b"\x00")
            metadata[keyword.decode("latin-1")] = rest[2:].split(b"\x00", 2)[-1].decode(
                "utf-8", errors="replace"
            )
        elif chunk_type == b"zTXt":
            keyword, _, rest = chunk_data.partition(b"\x00")
            try:
                metadata[keyword.decode("latin-1")] = zlib.decompress(
                    rest[1:]
                ).decode("latin-1", errors="replace")
            except zlib.error:
                metadata[keyword.decode("latin-1")] = "<unreadable>"
        if chunk_type == b"IEND":
            break
        offset += 12 + length
    return metadata


def demo():
    """最小演示：应用样式 -> 画一条示例线 -> 剥离保存 -> 自检元数据。
    仅验证工具链；演示输出不是项目结果，不得进入论文。"""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    apply_production_style(plt)
    figure, axis = plt.subplots(figsize=(7.2, 4.6))
    axis.plot([0, 1, 2], [1.0, 2.0, 1.5], color=SERIES_COLORS[0],
              marker="o", label="示例序列（非项目数据）")
    axis.set_title("style demo")
    axis.legend(frameon=False)
    output = Path("figures_style_demo.png")
    save_stripped(figure, output)
    plt.close(figure)
    metadata = png_text_metadata(output)
    print("saved:", output)
    print("metadata keys:", sorted(metadata))
    print("Software stripped:", "Software" not in metadata)


if __name__ == "__main__":
    demo()
