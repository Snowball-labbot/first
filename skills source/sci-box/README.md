# sci-box

[English](README_EN.md)

面向科研工作的开源 Agent Skills 合集。

sci-box 提供一组可直接调用的科研绘图与论文示意图模板，帮助 Agent 快速产出高质量图表与可编辑矢量图。

## 使用

```
npx skills add jihe520/sci-box
```

## Skills

### `scibox-figure` · 科研绘图复刻模板

基于 Python + Matplotlib 的科研绘图模板集合，支持 SHAP、ROC、Taylor、Raincloud、Chord、Circular Heatmap 等图表类型，一键渲染出 PNG / PDF / SVG。

![科研绘图复刻模板合集](docs/cover.png)

### `scibox-diagram` · 论文示意图模板（draw.io）

产出**可编辑**的 draw.io / diagrams.net 示意图（`.drawio` + PNG/PDF）。内置四套模板：五带技术路线图、三栏研究框架图、三栏阶段流程图、横版任务流水线图；另有从零手写 XML 与高保真复刻参考图两条路径，并附静态排版检查、浏览器预览与导出脚本。

![论文示意图模板合集](docs/cover-diagram.png)

## 第三方素材

`skills/scibox-diagram/assets/icons/tabler/` 为 Tabler Icons（MIT），详见
[ATTRIBUTION.md](skills/scibox-diagram/ATTRIBUTION.md)。
