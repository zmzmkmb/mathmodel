---
name: 5writing
description: "数学建模竞赛论文撰写阶段，支持 Typst 和 LaTeX 双引擎。根据 ANALYSIS_MODELING_REPORT.md、RESULTS_REPORT.md 和 figures/*.pdf 选择比赛模板、排版引擎、组织章节，并在论文正文中按章节直接插入图表。"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, WebSearch, WebFetch
---

# 竞赛论文撰写（Typst / LaTeX）

本 skill 承接 `3coding-visual` 和 `4drawio`。前序阶段只提供真实数据、图表 PDF 和记录文件；本阶段负责选择比赛模板和排版引擎、组织论文结构，并决定每张图表放入哪个章节。

开始前必须读取 `../_references/workflow_state_protocol.md` 和 `../_references/literature_protocol.md`，恢复已有状态后登记写作阶段：

```bash
python "<项目根>/backend/scripts/workflow_state.py" show
python "<项目根>/backend/scripts/workflow_state.py" stage --name writing --status in_progress
python "<项目根>/backend/scripts/literature_registry.py" init
```

**Typst 引擎**下可调用 typst-author skill 学习 typst 写法；**LaTeX 引擎**参考本文件末尾的"LaTeX 写作要点"小节。

## 数学建模规范参考

如需领域判断，读取 `../_references/math_modeling_norms.md` 中的”论文写作””图表与可视化”和”非数据图工具选择”小节。该文件只作为规范知识库，论文结构仍按比赛模板和当前赛题内容决定。

各章节写作技法优先通过本地动态检索获得；`../_references/writing_knowledge_base.md` 只在检索脚本失败或无匹配时作为静态兜底。

## 模板族

本技能内捆绑的模板位于：

```text
templates/zh/<竞赛>/main.typ         # Typst 模板
templates/zh/<竞赛>-latex/main.tex   # LaTeX 模板
templates/en/<竞赛>/main.typ         # Typst 模板
templates/en/<竞赛>-latex/main.tex   # LaTeX 模板
```

**LaTeX 模板覆盖范围**：所有中文模板和英文模板均已提供 LaTeX 版本（`-latex` 后缀），使用 xelatex 编译。

支持的中文模板（Typst + LaTeX 双版本）：

```text
apmcm, changsanjiao, cumcm, default, diangongbei, dongsansheng,
huashubei, huaweibei, huazhongbei, mathorcup, mcm, shuweibei, stats, wuyibei
```

华为杯、华中杯、五一杯统一使用 `huaweibei`、`huazhongbei`、`wuyibei` 作为模板。

支持的英文模板（Typst + LaTeX 双版本）：

```text
apmcm, default, mcm
```

论文中的所有数值图表结论必须来自 `reports/RESULTS_REPORT.md` 或 `figures/*`。不得编造、估算或使用不同的四舍五入方式。


## 工作流

### 步骤 0：确定排版引擎

**撰写论文前必须让用户选择排版引擎。** 引擎决定后续所有步骤（模板路径、章节文件扩展名、图片插入语法、编译命令），选错会导致整篇论文格式错误。

使用 AskUserQuestion 工具向用户询问："撰写论文使用哪种排版引擎？"

- 选项 1：LaTeX（xelatex 编译，数学建模竞赛主流，模板已全部就绪）— 推荐选项放第一位
- 选项 2：Typst（typst 编译，调用 typst-author skill 辅助写作）

询问前先读取 `plan.md` 的"用户偏好 → 排版引擎"字段作为预选项：
- 若 plan.md 已记录引擎选择，向用户确认："检测到之前选择的引擎是 <LaTeX/Typst>，是否沿用？"
- 若 plan.md 不存在或未记录引擎选择，直接询问用户选择。
- 若用户未明确指定或跳过，**默认使用 LaTeX**。

根据确定的引擎选择对应模板族：

- **Typst 引擎**：使用 `templates/<lang>/<竞赛>/main.typ`，调用 typst-author skill。编译命令 `typst compile main.typ`。
- **LaTeX 引擎**：使用 `templates/<lang>/<竞赛>-latex/main.tex`，xelatex 编译（中文和英文均需跑两遍解决交叉引用）。编译命令 `xelatex -interaction=nonstopmode main.tex`（执行两次）。

**后续步骤中的所有代码示例、文件扩展名、图片插入语法都必须按所选引擎选择对应版本，不要混用。**

### 步骤 1：选择语言和模板


除非用户明确要求中文，否则 MCM/ICM/COMAP 一律使用英文。所有中文竞赛名称使用中文。

模板键示例（Typst 引擎）：

```text
长三角 -> zh/changsanjiao
APMCM 英文版 -> en/apmcm
全国赛/国赛/CUMCM -> zh/cumcm
统计建模 -> zh/stats
MCM/ICM/COMAP -> en/mcm
```

模板键示例（LaTeX 引擎）：

```text
全国赛/国赛/CUMCM -> zh/cumcm-latex
MCM/ICM/COMAP -> en/mcm-latex
```

### 步骤 2：准备模板

用以下命令检查捆绑模板是否可访问（`SKILL_DIR` 为本 skill 所在目录）：

**Typst 模板**：

```bash
ls "$SKILL_DIR/templates/zh/<竞赛>/main.typ" 2>/dev/null && echo "OK" || echo "MISSING"
```

- **文件存在（OK）**：直接将 `templates/zh/<竞赛>/` 整目录复制到 `paper/`。这些模板是自包含入口文件，不依赖额外共享样式文件。
- **文件不存在（MISSING）**：说明 skill 未完整安装或在沙箱中，此时依照本 SKILL.md 步骤 3 列出的对应节文件结构，从零重建最小可编译 Typst 框架，并在 `paper/` 内注明"重建自 default 结构"。

存在匹配模板时，绝不从零开始写论文。

**LaTeX 模板**：

```bash
ls "$SKILL_DIR/templates/zh/<竞赛>-latex/main.tex" 2>/dev/null && echo "OK" || echo "MISSING"
```

- **文件存在（OK）**：将 `templates/zh/<竞赛>-latex/` 整目录复制到 `paper/`。
- **文件不存在（MISSING）**：说明 skill 未完整安装或在沙箱中，此时依照本 SKILL.md 步骤 3 列出的对应节文件结构，从零重建最小可编译 LaTeX 框架，并在 `paper/` 内注明"重建自 default-latex 结构"。


### 步骤 3：构建图表规划

在写正文各节之前，根据 `figures/*.pdf`、`reports/RESULTS_REPORT.md`，以及 `reports/DRAWIO_REPORT.md`（如果存在）构建图表规划：

```text
图表规划
fig_roadmap.pdf -> 引言/问题重述
fig_flow_q1.pdf -> 问题一模型构建
fig_flow_q2.pdf -> 问题二模型构建
fig_pipeline.pdf -> 数据预处理/方法节
结果图 -> 对应的结果节
```

图片路径相对于写入该图片的文件：写在 `paper/main.typ` 或 `paper/main.tex` 中通常用 `../figures/xxx.pdf`，写在 `paper/sections/*.typ` 或 `paper/sections/*.tex` 中通常用 `../../figures/xxx.pdf`。

**Typst 引擎**图片插入：

```typst
#figure(
  image("../../figures/fig_q1_error_dist.pdf", width: 85%),
  caption: [问题一预测误差分布],
)
```

**LaTeX 引擎**图片插入：

```latex
\begin{figure}[H]
  \centering
  \includegraphics[width=0.85\textwidth]{../../figures/fig_q1_error_dist.pdf}
  \caption{问题一预测误差分布}
  \label{fig:q1_error}
\end{figure}
```

英文论文使用英文图注。

### 步骤 4：查阅写作知识库（必须执行！）

在撰写每类章节之前，**必须分别调用**本地检索脚本，按当前题目、模型和论证重点传入关键词。例如：

```bash
python "<项目根>/backend/scripts/search_writing_knowledge.py" \
  --section-type "摘要" \
  --keywords "预测,优化,鲁棒性" \
  --top 3 \
  --format markdown
```

至少分别检索：`摘要`、`问题分析`、`模型假设`、`模型建立与求解`、`敏感性分析`、`模型评价`。图表密集或公式复杂时，再检索 `图表解读`、`公式排版`。不要用一次宽泛检索替代逐章节检索。

动态条目包含：

- **技法**：该章节的写作技巧
- **范文片段**：可直接参考的写作范例
- **为什么有效**：从评委视角解释
- **推荐做法** 和 **避免做法**

撰写每个章节时，先使用返回的技法条目，再动笔。例如写摘要前检索三段式摘要结构，写模型假设前检索 Justification。只有脚本报错或明确返回无匹配时，才读取 `../_references/writing_knowledge_base.md` 的对应章节兜底，并在临时笔记中记录兜底原因。

将查阅过的技法条目记录到 `paper/` 下的临时笔记中（写完论文后可删除），确保每个章节的写作都参考了知识库中的技法。

### 步骤 5：撰写各节

**以下章节文件名按所选引擎使用 `.typ`（Typst）或 `.tex`（LaTeX）扩展名。** 例如 Typst 引擎用 `1_restatement.typ`，LaTeX 引擎用 `1_restatement.tex`。文件名主体保持一致。

中文数学建模通用模板各节文件（`changsanjiao`、`diangongbei`、`huashubei`、`mathorcup`、`wuyibei`）：

```text
1_restatement.typ  - 问题重述与分析
2_analysis.typ     - 数据理解与总体思路
3_assumptions.typ  - 模型假设
4_symbols.typ      - 符号说明
5_problem1.typ     - 问题一建模与求解
6_problem2.typ     - 问题二建模与求解
7_problem3.typ     - 问题三建模与求解
...         - 根据题目调整问题数量  
8_evaluation.typ   - 灵敏度分析、模型评价与推广
A_code.typ         - 附录代码
```

国赛/华中杯/华为杯（`cumcm`、`huazhongbei`、`huaweibei`）按以下章节结构：

```text
1_restatement.typ
2_analysis.typ
3_assumptions.typ
4_symbols.typ
5_problem1.typ
6_problem2.typ
7_problem3.typ
...        - 根据题目调整问题数量
8_sensitivity.typ
9_evaluation.typ
A_code.typ
```

东三省模板（`dongsansheng`）额外使用单独摘要文件：

```text
abstract.typ
1_restatement.typ
2_analysis.typ
3_assumptions.typ
4_symbols.typ
5_problem1.typ
6_problem2.typ
7_problem3.typ
...       - 根据题目调整问题数量
8_evaluation.typ
A_code.typ
```

数维杯模板（`shuweibei`）保留原 LaTeX 的示例入口命名：

```text
Abstract.typ
Introduction.typ
2_analysis.typ
3_assumptions.typ
4_symbols.typ
5_problem1.typ
6_problem2.typ
7_problem3.typ
...      - 根据题目调整问题数量
8_evaluation.typ
Appendices1.typ
A_code.typ
```

中文默认模板（`default`）：

```text
1_restatement.typ
2_assumptions.typ
3_symbols.typ
4_problem1.typ
5_problem2.typ
6_problem3.typ
...      - 根据题目调整问题数量
7_sensitivity.typ
8_evaluation.typ
A_code.typ
```

中文统计建模各节文件：

```text
1_introduction.typ
2_method.typ
3_data.typ
4_analysis.typ
5_results.typ
6_conclusion.typ
A_code.typ
```

英文 MCM/APMCM 各节文件（`en/mcm`、`en/apmcm`、`zh/mcm`、`zh/apmcm`）：

```text
1_introduction.typ
2_assumptions.typ
3_model_design.typ
4_solution.typ
5_sensitivity.typ
6_strengths_weaknesses.typ
7_conclusions.typ
A_code.typ
```

**LaTeX 模板章节文件**（对应 `-latex` 后缀模板，结构与 Typst 版本一一对应）：

国赛 LaTeX 模板（`zh/cumcm-latex`，对应 `cumcm` Typst 版本）：

```text
1_restatement.tex
2_analysis.tex
3_assumptions.tex
4_symbols.tex
5_problem1.tex
6_problem2.tex
7_problem3.tex
8_sensitivity.tex
9_evaluation.tex
A_code.tex
```

MCM/ICM LaTeX 模板（`en/mcm-latex`）：

```text
1_introduction.tex
2_assumptions.tex
3_model_design.tex
4_solution.tex
5_sensitivity.tex
6_strengths_weaknesses.tex
7_conclusions.tex
A_code.tex
```

其余 LaTeX 模板（`changsanjiao-latex`、`default-latex`、`huashubei-latex`、`mathorcup-latex`、`wuyibei-latex`、`huazhongbei-latex`、`huaweibei-latex`、`diangongbei-latex`、`dongsansheng-latex`、`shuweibei-latex`、`stats-latex`、`apmcm-latex`、`mcm-latex`、`en/apmcm-latex`、`en/default-latex`）的章节文件命名与上述结构类似，以 `main.tex` 中 `\input{}` 引用的文件名为准。

英文默认模板（`en/default`）：

```text
1_introduction.typ
2_assumptions.typ
3_notations.typ
4_model.typ
5_sensitivity.typ
6_evaluation.typ
7_conclusions.typ
A_code.typ
```

**正文写作应使用连贯的学术段落。避免在最终论文中出现工作流内部名称，如 `reports/`、`figures/` 或 `CLAUDE.md`。**

#### 段落式写作规范（强制！）

**严格禁止分点式论述（bullet points / numbered lists）出现在正文中。**
必须将分点式内容转换为流畅的论文级段落式语言。

❌ 错误示例：
```
关键发现：
1. 右偏分布：大多数国家奖牌数较少
2. 均值 > 中位数：数据被高奖牌数国家拉高
3. 异常值：超级强国奖牌数远高于平均水平
```

✅ 正确示例：
```
分布分析揭示了奖牌数据的若干显著特征。大多数国家获得的奖牌数较少，
中位数仅为5枚，而少数强国累积了显著更高的总量，形成了右偏分布。
均值超过中位数进一步证实了这一点，表明平均值被高表现国家抬高。
此外，美国和前苏联等国家的奖牌数远超典型水平，构成统计意义上的异常值。
```

#### 章节篇幅占比指南

| 章节 | 篇幅占比 | 核心功能 |
|------|---------|---------|
| 摘要 | 1页 | 最重要！概述问题、方法、结果、结论 |
| 问题重述 | 8-12% | 问题背景、重述、研究内容概述 |
| 问题分析 | 8-12% | 每个问题的分析思路 |
| 模型假设 | 适量 | 假设 + Justification |
| 符号说明与数据预处理 | 适量 | 符号表 + EDA 描述性统计 |
| 模型建立与求解 | 50-60% | 各问题的模型构建与结果 |
| 敏感性分析 | 4-8% | 参数敏感性与稳健性验证 |
| 模型评价 | 4-8% | 优势与局限性讨论 |

#### 过渡连接词

| 类型 | 中文 | 英文 |
|------|------|--------|
| 递进 | 此外、进一步地、同时 | Furthermore, Moreover, Additionally |
| 因果 | 因此、由此可见、据此 | Therefore, Thus, Consequently |
| 转折 | 然而、但是、与此相对 | However, Nevertheless, In contrast |
| 举例 | 例如、以……为例、具体而言 | For example, Specifically, As illustrated by |
| 总结 | 综上所述、总体而言 | In summary, To conclude, Overall |

#### 语态与时态

- 中文论文：客观陈述为主，避免"我们"过多。使用"本文""本研究"。
- 英文论文：被动语态为主强调客观性（The model was trained using...）；主动语态强调研究贡献（We develop a novel framework...）
- 现在时：描述模型、公式、一般性结论
- 过去时：描述实验过程、数据处理步骤

#### 避免事项

- 避免口语化表达（"很多"→"大量"，"a lot of"→"numerous"）
- 避免主观评价词（"非常好"→ 用数据支撑）
- 避免过长句子（每句不超过30词）
- **禁止分点列表出现在正文论述中**

#### 参数定量依据（关键检查项）

所有模型参数都必须有明确来源，禁止出现无解释的"默认值"：
- 参数来源三选一：**数据统计** / **文献引用** / **校准实验**
- 阈值选择需有敏感性分析或样本量说明
- 写论文时逐个检查：公式中每个参数是否说明了"从何而来"

#### 模型选择论证

选择任何模型必须在论文中包含：
1. 为什么选这个模型（1-2 句）
2. 与备选方案的对比（表格或段落）

#### 因果 vs 相关区分

预测准确率高 ≠ 因果关系！数据分析型题目必须在论文中明确声明：
```
虽然统计检验表明[模式]存在，但这并不证明因果关系。
替代解释包括[替代解释1]、[替代解释2]等。
```

#### 图片解读规则（强制！）

**每幅图表至少配 3 行分析文字**，说明趋势、原因、与结论的关系。禁止"只放图不解释"。
图表描述必须基于代码手输出的实际数据特征（见 `RESULTS_REPORT.md` 和代码 print 输出），禁止编造数值。

引用句式：
- 引入：如图 X 所示，[图表核心内容]。
- 解读：图 X 展示了……表明……
- 对比：与[对比对象]相比，[研究对象]在[指标]上……

#### 引用协议

1. 同一文献在 `data/literature.json` 和参考文献表中只登记一次
2. 正文可在多个必要位置复用同一个稳定引用键，不要为重复引用创建新条目
3. 添加引用前先核对登记表中的作者、题名、年份、DOI/URL 和核验来源
4. 参考文献必须真实存在，不编造；`unverified` 条目不得导出
5. 理论性章节（引言、方法论）应引用真正支撑模型来源、假设或对比依据的文献

### 步骤 6：参考文献

只使用真实存在且已经核验的参考文献。WebSearch/WebFetch 负责搜索和打开来源，本地登记表负责去重、校验和导出；不调用旧 Web 后端或 OpenAlex Agent。

每找到一篇实际采用的文献，就登记真实元数据和正文用途：

```bash
python "<项目根>/backend/scripts/literature_registry.py" add \
  --id ref1 \
  --title "<真实题名>" \
  --authors "Author A;Author B" \
  --year 2024 \
  --venue "<期刊或会议>" \
  --doi "10.xxxx/xxxx" \
  --verified-source "DOI landing page" \
  --used-in "模型建立" \
  --verification-status verified
```

完成检索和登记后先运行硬校验，再按引擎导出。校验失败时必须修正文献元数据，不能手写绕过：

```bash
python "<项目根>/backend/scripts/literature_registry.py" validate
python "<项目根>/backend/scripts/literature_registry.py" export --format typst --output paper/references.typ
python "<项目根>/backend/scripts/literature_registry.py" export --format latex --output paper/references.tex
```

只执行与所选引擎对应的导出命令。文件名按引擎选择：Typst 用 `paper/references.typ`，LaTeX 用 `paper/references.tex`。

**Typst 引擎**：

```typst
#set enum(numbering: "[1]")
#enum[
  作者. 题名[J]. 期刊名, 年份, 卷(期): 页码.
  Author. "Title." Journal or Conference, year.
]
```

正文上标引用：`相关研究已用于物流网络优化#super("[1]")。`

**LaTeX 引擎**：

```latex
\begin{thebibliography}{99}
  \bibitem{ref1} 作者. 题名[J]. 期刊名, 年份, 卷(期): 页码.
  \bibitem{ref2} Author. "Title." Journal, year.
\end{thebibliography}
```

正文引用用 `\cite{ref1}` 或 `\cite{ref1,ref2}`。

### 步骤 7：最后撰写摘要或总结

在所有章节完成后撰写中文摘要或英文 Summary Sheet。必须包含每个子问题的方法和精确的数值结果。

### 步骤 8：登记写作产物

论文正文、参考文献和登记表都存在且文献校验通过后，登记实际入口文件并完成阶段：

```bash
python "<项目根>/backend/scripts/workflow_state.py" artifact --name paper_main --file paper/main.tex --required
python "<项目根>/backend/scripts/workflow_state.py" artifact --name references --file paper/references.tex --required
python "<项目根>/backend/scripts/workflow_state.py" artifact --name literature_registry --file data/literature.json --required
python "<项目根>/backend/scripts/workflow_state.py" stage --name writing --status completed --note "论文正文与已核验参考文献已生成"
```

Typst 项目将上述 `.tex` 路径替换为 `.typ`；不要同时登记不存在的另一种引擎文件。

## LaTeX 写作要点

以下要点供 **LaTeX 引擎**使用。Typst 引擎请调用 typst-author skill 获取语法帮助。

### 编译命令

```bash
# 中文模板（xelatex，跑两遍解决交叉引用）
xelatex main.tex && xelatex main.tex

# 英文模板（xelatex，同样跑两遍）
xelatex main.tex && xelatex main.tex
```

### 文档结构

```latex
\documentclass[a4paper,12pt]{article}   % 英文
\documentclass[a4paper,12pt]{ctexart}   % 中文

\usepackage{...}   % 宏包加载
\usepackage{graphicx}   % 图片支持
\usepackage{booktabs}   % 三线表
\usepackage{amsmath,amssymb}   % 数学公式
\usepackage{hyperref}   % 交叉引用（需两遍编译）
```

### 图表插入

```latex
\begin{figure}[H]
  \centering
  \includegraphics[width=0.85\textwidth]{../../figures/fig_q1.pdf}
  \caption{图注}
  \label{fig:q1}
\end{figure}

% 三线表
\begin{table}[htbp]
  \centering
  \caption{表注}
  \begin{tabular}{ccc}
    \toprule
    \textbf{列1} & \textbf{列2} & \textbf{列3} \\
    \midrule
    数据 & 数据 & 数据 \\
    \bottomrule
  \end{tabular}
\end{table}
```

### 交叉引用

```latex
如图~\ref{fig:q1}所示，...   % 图片引用
式~(\ref{eq:objective}) 给出...   % 公式引用
见第~\pageref{fig:q1} 页   % 页码引用
```

### 数学公式

```latex
行内公式：$f(x) = \sum_{i=1}^n \theta_i \phi_i(x)$

行间公式：
\begin{equation}
  \mathcal{L}(\theta) = \frac{1}{N}\sum_{i=1}^N (y_i - \hat{y}_i)^2
  \label{eq:objective}
\end{equation}
```

### 章节和强调

```latex
\section{问题重述}
\subsection{问题背景}
\textbf{问题一：} xxx   % 对应 Typst 的 #strong
```
