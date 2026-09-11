# 第三、四问运行与检查点

先读根目录 `题目分析报告.md` 的结算、预报与时间合同。代码沿用前两问物理单位和因果执行口径，不覆盖其结果。训练 CPU PyTorch 2.14.0+cpu，单线程，运行命令从仓库根目录执行：

```text
python -X utf8 -m unittest discover -s tests -v
python -X utf8 -m src.q34_data --data-root <原始C题目录>
python -X utf8 -m src.q34 --data-root <原始C题目录> --out artifacts/q34-smoke --smoke
python -X utf8 -m src.q34 --data-root <原始C题目录>
python -X utf8 -m src.q4_forecast --data-root <原始C题目录> --out artifacts/q34-smoke --smoke
python -X utf8 -m src.q4_run --data-root <原始C题目录> --out artifacts/q34-smoke --smoke
python -X utf8 -m src.q4_forecast --data-root <原始C题目录>
python -X utf8 -m src.q4_run --data-root <原始C题目录>
```

本机深度学习环境为 `.venv-q34/Scripts/python.exe`，由打包 Python 的 `venv --system-site-packages` 创建，仅在此隔离环境安装官方 CPU PyTorch。普通文档与 Excel 工具仍使用打包运行时。依赖目录不进 Git。

第三问 `q3_selection.json` 冻结一月验证选定的余量和更新时间子集；位掩码 1/2/4 分别为 06/12/18 点，0 表示只午夜，7 为全部更新。主结算退回取消部分原电价的50%；另一无退款口径独立重新求解，不能只更改已经算好的费用数字。午夜计划、有效执行计划、各次调整和紧急量分别存储。

第四问模型在 1月15/22日初始化，之后每月月初从最近60天重训，预测器输入均为已知的前一天、前一周同目标钟点曲线和日历。GRU 6维输入、32隐藏维度、一层、输出对同期曲线的残差；目标为未来144点，一次输出，不喂入未来真实价格。内部最近3天早停验证与训练目标无重叠；随机种子17/42/2026均保存，另以三次均值构成预先定义的集成。

价格比较先在一月选择岭惩罚与预测性能，再按两类调度各自一月实际总费用在同期、岭回归、GRU集成中选主方案。全年仍报告三个GRU种子的调度结果，不根据全年指标重新挑选主模型。所有时间戳按北京时间对应题面日期，午夜后的预报只用于尚未执行后缀。

每次模型拟合保存 `.pt` 与训练日志，生成价格 `.npz`；每个策略保存逐日和完整逐时轨迹，滚动方案额外保存计划版本。`q3_run_manifest.json`／`q4_run_manifest.json` 只有对应批次结束才写入，不存在时不说明已经完成。

当届官方比赛时间为9月10日18时至9月13日20时，来源：[中国工业与应用数学学会通知](https://www.csiam.org.cn/upload/shuxue/69c3870950b04.pdf)。电子论文格式以[2026官方规范](https://www.mcm.edu.cn/html_cn/node/4cd596519c9eb9fbd866398f6df0caa3.html)为准，论文正文≤30页，附录另计；最终平台操作时限另由参赛队核对。
