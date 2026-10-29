# 同类技能借鉴记录

维护与来源追溯时读取，普通任务不需要加载。下方四项固定提交及其核对结论继承自上传的 0.2.0-dev.10，原记录日期为 2026-10-27；不将它们说成本轮重新验证的提交。本轮 2026-10-28 实际读取的来源另列于后。这里只记录方法借鉴与本项目的取舍，未复制第三方技能正文、代码或模板，也不把对方的工作流当作当前任务指令。

## 来源与融合

| 来源 | 值得吸收的部分 | 在本技能中的变化 | 未采用的部分 |
| --- | --- | --- | --- |
| [Superpowers · brainstorming](https://github.com/obra/superpowers/blob/2ce8aa15d05bd57213e6f746f953aafb7ded7a8b/skills/brainstorming/SKILL.md)，obra | 结合已有材料比较真实替代路线；关注形式成功但用户仍不能接受的结果；通过小样讨论取舍 | 主文件设计阶段增加有差异的候选、共同比较依据与改选条件；高度部分关注背离目的的结果 | 不固定要求二至三案、设计文档审批、每轮一个问题、提交文件或转入其他技能；已有授权直接推进 |
| [Scientific Agent Skills · scientific-brainstorming](https://github.com/K-Dense-AI/scientific-agent-skills/blob/a92663a0214b3b9fa1ba6b958284ffd919c00a0c/skills/scientific-brainstorming/SKILL.md)，K-Dense，元数据版本 1.4 | 发散和评价分开；候选按结构差异区分；先明确比较依据，保留反证与分歧 | 设计方法中先探索机制差异再筛选；团队情境按需考虑独立发想；模型自拟候选不称为独立共识 | 不搬入科研专用审查、评分工具或整套会议流程；不把方法名称、共识或分数当效果证据 |
| [Anthropic · doc-coauthoring](https://github.com/anthropics/skills/blob/00756142ab04c82a447693cf373c4e0c554d1005/skills/doc-coauthoring/SKILL.md) | 通过不掌握作者聊天上下文的读者发现遗漏；围绕具体问题局部修稿 | 主文件增加独立使用检查；设计方法区分作者自查与真实独立读者测试 | 不采用固定五至十个问题、逐节确认或自动调用读者代理；不把反复自查声称为独立验证 |
| [Seth Hobson · prompt-engineering-patterns](https://github.com/wshobson/agents/blob/511f8345cf42f84676e0ad56ddfdee33c90a666f/plugins/llm-application-dev/skills/prompt-engineering-patterns/SKILL.md) | 样例选择、变量化模板、按具体失败迭代、代表性输入比较 | 设计方法补足稳定规则／输入／材料边界、缺失处理、对照样例和近邻回归 | 不复制模型/API 示例，不默认要求展示内部推演、固定自信度阈值、外部依赖或多次模型采样 |

提示词模式还核对了同一仓库当次默认分支的 `references/details.md`，用于理解样例、渐进增加复杂度与错误处理的用法；融合规则以这里列明的通用机制为限，不移植其代码或数值。

## 如何避免只增加篇幅

现有技能已具备按上下文澄清、观察与推断分离、可检验机制、跨领域迁移和授权边界。相近来源中的这些重合部分继续沿用原文，不重复堆叠。新增内容集中于四个原先较少展开的动作：产生不同候选、用小样辨别取舍、补足独立使用所需上下文、从失败样例修复提示词。

共用的判断保留在 [SKILL.md](../SKILL.md)，有条件才需要的操作放在 [设计方法](design-methods.md)。行为案例用于观察候选是否真的不同、示例是否带入虚构事实、是否擅自启动代理，以及修复后是否误伤正常任务，见 [行为评估案例](behavior-evals.md) 第 17–22 项。

这是方法来源与设计理由，不是效果报告。源技能的知名度、安装量、作者身份及其自身的效果声明，都不能证明融合后的版本更好；新增案例尚需实际执行，之后才能报告对应条件下的行为表现。

## 2026-10-28：理解需求与结果验证的补强

维护版本为 0.2.0-dev.11。本节链接为本轮实际打开的上游页面，默认分支和文档日后可能变化，不声称它们是固定快照。主文件新增的判断规则为本项目的综合设计，不是任何来源的官方统一框架。

| 本轮核对来源 | 吸收并落实的位置 | 未采用的部分 |
| --- | --- | --- |
| [Superpowers brainstorming](https://raw.githubusercontent.com/obra/superpowers/main/skills/brainstorming/SKILL.md) | 先读取上下文，辨别目标、现状与不可接受结果；落实到主文件任务理解及 context-intake.md。按错误代价改写澄清分流。 | 不要求每轮都以问题结束，不机械安排选案、批准设计文档等前置门槛。 |
| [Superpowers writing-plans](https://raw.githubusercontent.com/obra/superpowers/main/skills/writing-plans/SKILL.md) | 将准确约束和完成依据传到执行端；落实到 design-methods.md 的信息覆盖与自包含检查。 | 不搬入所有任务必须 TDD、固定提交或工作树的流程。 |
| [Anthropic skill-creator](https://raw.githubusercontent.com/anthropics/skills/main/skills/skill-creator/SKILL.md) | 从已有对话提取意图、纠正和输出形式；保留基线并针对具体问题修订。详细方法按需读取。 | 不把强势触发描述、固定访谈和整套评测当作每次优化提示词的必经动作。 |
| [Anthropic blind comparator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/agents/comparator.md) 与[官方评估指导](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests) | 按任务定义成功，区分提示词设计与执行结果；对照时可匿名评议并保留持平和退化，落实到 design-methods.md。 | 不将模型评分、单次通过或一组开发案例解释为稳定性能提升；不照搬无依据的指标目标。 |
| [Anthropic prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) | 明确上下文、输出、约束和资料边界；示例按需加入，模型相关技巧单独核实。 | 不将某模型的参数、固定标签格式、强语气或多代理习惯当作通用要求。 |

本次对原版已有的候选比较、独立读者检查、近邻回归和证据边界予以保留，不将其包装成新功能。新变化集中在任务相关用户信息、澄清代价分流、必要视角的广度，以及仅优化提示词时不提前制造研究结论。敏感信息最小化与历史偏好时效是本项目为共享提示词作出的明确设计选择。

旧版评估只支持对应版本和条件。本轮开发检查与后续真实使用效果须分别记录；本文件中的方法来源不构成性能证据。

## 2026-10-28：dev.12 的可见对齐与表达

本次针对执行前看不见理解与改动、逐轮追问负担、缺少背景表达支架作局部修订。主文件与 context-intake.md 负责可见对齐和澄清收敛；clear-expression.md 负责表达清楚且保留原意；design-methods.md 补充对话过程的验证边界。

| 核对来源 | 采用部分 | 未采用与限制 |
| --- | --- | --- |
| Matt Pocock 的 [grill-me 入口](https://github.com/mattpocock/skills/blob/main/skills/productivity/grill-me/SKILL.md)、[grilling](https://github.com/mattpocock/skills/blob/main/skills/productivity/grilling/SKILL.md) 及[作者说明](https://github.com/mattpocock/skills/blob/main/docs/productivity/grilling.md) | 事实先查；区分事实与用户决定；将可独立回答的关键问题集中询问；执行前核对理解。 | 当前版本已按决策依赖分轮提问，不能一概说成逐题旧版；它仍以遍历全部决策分支为终点。这里改为足以完成当前交付即收敛，不问完所有分支，不机械要求每个决定都由用户回答。 |
| [ASD-STE100 官方 FAQ](https://www.asd-ste100.org/STE_faq.html) 与 [Issue 9 标准](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf) | 借鉴术语一致、动作明确、短而清楚的表达，以及让先决条件容易识别。 | 官方直接抓取受限，原则依据官方索引正文核对；不声称完成全文合规审查。中文不套英文词典与英文词数限制；表达规范不能替代需求理解。 |

每轮通常 1–3 个关键问题、答复后形成可用任务说明，以及区分“展示”与“等待”，是本技能基于交互需求作出的设计选择，不是上述来源证明的最佳参数。

关于用户提到的 Karpathy：检索线索指向 https://x.com/karpathy/status/2105819303471976479 ，但本轮未能直接读取原帖，故不引述其原话、不将“80% STE”等转载表述当成标准或效果依据。STE 的使用理由依据官方语言原则与本任务需要。
