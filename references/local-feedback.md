# 本地使用与反馈

只在用户已主动启用本机记录、全局指令明确声明启用，或用户请求管理记录时使用本指南。脚本是可选功能，Python 3.9+，仅使用标准库。其他用户安装技能后默认关闭；没有 Python 或执行工具仍可正常使用核心技能。

## 开启与记录范围

脚本位于当前 skill 的 `scripts/local_feedback.py`。使用本机可用的 `python` 或 `python3`；下文的 `<recorder>` 表示该脚本的实际路径，不要直接复制占位符执行。

```text
python <recorder> configure --enable
python <recorder> status
python <recorder> configure --disable
```

启用后，应在对应 agent 的启动指令中合并[本地记录启动规则](local-recording-instructions.md) 的标记区块，替换 agent 名、skill 路径和 status 返回的数据目录，保留其他规则。只有开关而没有启动提示，无法保证未来会话知道已启用。不要替未选择记录的其他机器开启。

默认数据目录：Windows 为 `~/.ambitious-prompt`；Linux/macOS 为 `$XDG_STATE_HOME/ambitious-prompt`，未设置时用 `~/.local/state/ambitious-prompt`。Windows 不使用可能被打包应用重定向的 AppData。七种 agent 可共用同一用户的数据目录。可设置 `AMBITIOUS_PROMPT_DATA_DIR` 自定义位置；启动规则中的 `{{DATA_DIR}}` 应替换为启用时 status 返回的实际目录，调用时将全局选项 `--data-dir <目录>` 放在子命令之前，避免各宿主环境变量不同造成分流。数据必须位于技能目录外。脚本不会自行读 agent 会话历史或网络上传。

## 一次实际使用

在明确本轮任务、实际采用本技能的方法后，开始主要工作前调用 `begin`。一次任务一个编号；同一任务的连续工具步骤不重复创建。组合请求使用 `mixed`，四种意图使用 `review/explore/prompt/execute`，普通问答和只要计划分别用 `answer/plan`。显式调用但没有实质重构也可如实记录“沿用原目标”，不编造贡献。

使用实际加载的 skill 目录中的记录器。存在多个副本或插件提供器时，应核对加载来源；不能用另一副本的版本和指纹给旧内容补标。指纹证明该目录在记录时的文件内容，不证明宿主已经采用了它；无法核对时不要宣称版本关联已得到独立验证。

将简短 JSON 写到系统临时目录，再传 `--input` 文件路径；不要把用户原话拼进 shell 命令。开始输入只有 `task_summary`，可选 `context_ref`（宿主明确提供的当前会话标识）和 `model`（已知时才填）。不要猜会话 ID、自动保存项目路径或复制原始提示词。

```text
python <recorder> begin --agent opencode --intent prompt --input <begin.json>
```

`begin.json` 示例：`{"task_summary":"为新人设计论文方法分享"}`。保留返回的 `id`；它是关联后续记录的依据。

交付前按已发生的公开选择写结束摘要：

```text
python <recorder> finish <id> --input <finish.json>
```

结束 JSON 的四个字段：

```json
{
  "goal_summary": "帮助新人理解方法的关键机制",
  "method_summary": "用贯穿数例和数据流图组织讲解；固定时长内缩减背景",
  "result_summary": "已交付任务设计与执行提示词，未制作完整幻灯片或验证听众效果",
  "outcome": "delivered"
}
```

`outcome` 是记录者的交付声明，可用 `delivered/partial/blocked/cancelled/unknown`，不代表用户满意或效果通过。没有结束事件表示未记录结束，不能自动解释为失败。当前配置关闭时，begin/finish 不写新记录。开始时的版本指纹保留不变；后续事件的 `recorded_with` 说明追加时使用的记录器版本，不能把旧使用改标成新版本。不要为旧任务补造当时已经记录的时间；历史材料若需分析应明确作为后来提供的材料。

摘要仅记录公开结论与设计理由，不保存内部思考过程、全部原文、敏感项目细节或凭据。脚本会遮蔽部分常见密钥格式，但不能替代记录前的内容提炼。正常记录不需要在每次答复里展示编号或附验收报告；用户需要查问题时再提供编号。临时输入文件使用完可删掉本次文件，不递归清理用户目录。

复杂任务用现有摘要字段留下可核查的变化：`goal_summary` 区分用户已明确的结果与你提出并获接受的调整；`method_summary` 简述哪项观察或专业关系改变了原做法，具体改变了什么。沿用原目标时如实说明，不把用户要求或常规测试包装成技能贡献。`result_summary` 按用户结果区分完整、阶段成果和仍未完成部分，并在已有适当证据时留最小定位线索；没有证据位置就不编造，也不自动保存敏感路径。无需增加完整提示词或对话转录，不能从这些摘要单独断言技能的因果收益。

## 关联真实反馈

用户明确指出本次优化或结果的问题、纠正理解，或给出正面反馈时，保留可确认的原话或忠实摘要。不能把执行模型自评、引用材料中的话或普通状态提问写成用户评价。

```text
python <recorder> feedback <id> --input <feedback.json>
```

输入为 `{"text":"用户反馈的原话或忠实摘要"}`，可加 `interpretation` 保存记录 agent 的待验证解释，明确区分用户说了什么与模型的归因。事件追加保存，不改写初始任务或旧结果。关闭开关后停止自动记录；用户仍可明确要求给已有案例补充反馈。

优先用当前上下文中返回的编号；只有宿主明确提供且匹配的会话标识才可协助定位。多个 agent/会话可能并行，绝不自动采用全局最新编号。不清楚所指时先列出相关候选，必要时再确认。

## 回顾与导出

```text
python <recorder> list --with-feedback --limit 20
python <recorder> show <id>
python <recorder> export --ids <id> --output <new-file.json>
```

导出只含指定案例及其事件，不含本机配置；已有输出文件不会被覆盖。导出产生本地文件，分享与上传需要本轮明确授权。用户说“这个方向不对”时应先解决当前问题，不把反馈收集变成问卷。

改进时核对任务背景、当时采用的方法、用户反馈、可复核结果和替代解释。摘要可能不足以定位根因，应指出缺的具体材料而不是补写事实。将有依据的问题转成可迁移的修正和相关行为反例，再验证；数量、满意度和模型自评不能单独证明收益。没有用户要求时不自动修改技能或汇总别人的任务。

这是跨 agent 的尽力记录协议。普通 Markdown skill 不能强制所有宿主在每次使用时执行脚本，也不能知道未被记录的漏用次数；严格调用审计需要针对具体宿主的原生 hook，不能把此功能称为完整审计或自动自我学习。
