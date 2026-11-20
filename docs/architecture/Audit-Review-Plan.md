# 审计复核回路计划书

> 日期：2026-11-18  
> 状态：计划，不写代码  
> 目的：用“答案级证据账本”替代领域/锚点人工分类

---

## 1. 核心模型

```text
问题
  -> 召回句子集合
  -> 每句的来源、文章、页码、得分
  -> 大模型实际引用了哪些句子
  -> 证据账本
  -> 人类按账本审核/修改
```

不是：

```text
先判断 query 属于哪个领域/锚点
再决定怎么审
```

---

## 2. 账本字段

每条答案必须能展开：

| 字段 | 含义 |
|---|---|
| `query` | 用户问题 |
| `answer_id` | 本次回答 |
| `claim` | 回答中的一条陈述 |
| `cited_sentence_ids` | 该 claim 实际引用的句子 |
| `retrieved_sentence_ids` | 本次召回的全部句子 |
| `sentence_text` | 句子原文 |
| `paper_id / title` | 出处 |
| `section / page / bbox` | 定位 |
| `retrieval_score` | 召回得分 |
| `rerank_score` | 重排得分 |
| `rank` | 最终排名 |
| `cited` | 是否被大模型引用 |
| `support_status` | 引用/验证状态 |
| `review_priority` | 人工优先看哪条 |

---

## 3. 人类看到什么

默认按**可疑程度**排序，而不是按领域分类：

```text
高优先：
  高召回得分但未被引用
  被引用但得分很低
  claim 没有 citation
  citation 指向不存在的句子
  facet 缺失
  provenance 不完整

普通：
  已引用且得分中高
  claim 有 citation
  来源完整
```

人类动作：

```text
accept        接受
add_evidence  补证据
remove_claim  删除无证据 claim
flag_missing  标记可能漏召回
rerun         要求重新检索
```

每个动作写入审计日志。

---

## 4. 人机复核与重写回路

科研人员不是只能“接受/拒绝”，而是可以：

```text
打回
  claim / citation / paper 不对
  -> 机器重新选证据
  -> 新草稿，不覆盖旧稿

挑选
  从召回句子/段落里勾选真正相关的证据
  -> 派发给大模型
  -> 只重写指定段落
  -> 新草稿 + 新 citation

复核
  新稿逐条 claim -> evidence
  -> 人工接受 / 继续打回
```

### 4.1 状态机

```text
draft_v1
  -> review
     -> reject_citation -> retrieve_alternatives -> draft_v2
     -> select_evidence  -> rewrite_scope       -> draft_v2
     -> request_more     -> retrieve_more       -> draft_v2
  -> verify
     -> accept
     -> reject -> draft_v3
```

任何一步都不覆盖旧版本。

### 4.2 打回

输入：

```text
answer_id
claim_id
evidence_id
reason
```

行为：

```text
不改写原稿
标记该 evidence 为 rejected
按 claim 重新检索/重排
返回 alternatives（带来源/得分）
```

人类确认后才生成新稿。

### 4.3 挑选后重写

输入：

```text
answer_id
claim_ids 或 paragraph_id
selected_sentence_ids
rewrite_instruction
```

行为：

```text
只允许使用 selected_sentence_ids + 明确允许的新检索
生成 draft_v2
列出每条 claim 使用的 evidence
```

如果新稿引用了未选中的句子：

```text
flag: out_of_scope_evidence
不自动接受
```

### 4.4 版本与审计

每个版本：

```text
version_id
parent_version_id
actor
action
reason
selected_evidence_ids
used_evidence_ids
claim -> evidence
created_at
```

原稿、打回记录、被拒证据都保留。

### 4.5 不允许

```text
不允许打回后静默重写
不允许删除被拒证据
不允许新稿引用未展示的来源
不允许人工修改后不留版本
不允许人工修改自动变成模型训练
```

人工修改是审计数据，不是自动反馈训练集。

---

## 5. 评级

不是给整个 query 一个“召回率等级”，而是给**每条证据**一个状态：

```text
supported      被引用 + 验证通过
weak           被引用 + 验证失败/低分
uncited_high   高分但未被引用
uncited_low    低分且未被引用
missing        应有但没有
```

聚合只用于监控：

```text
audit_coverage
review_burden
missed_evidence_rate
human_correction_rate
claim_support_rate
```

---

## 6. BO 的位置

BO 只做一件事：

```text
在固定审计覆盖下，减少需要人工复核的条目
```

不是：

```text
提高 recall -> 取消审计
```

评估 BO 时看：

```text
recall 是否上升
review_burden 是否下降
missed_evidence_rate 是否不上升
claim_support_rate 是否不下降
```

BO 仍然：

```text
独立插件
默认关闭
只读实验
不自动上线
```

---

## 7. 与 P2 论文的关系

P2 不再需要：

```text
domain 标注
anchor_type 标注
query_type 人工分类
```

P2 的主线：

```text
RQ1 高 recall 时，账本是否仍暴露问题
RQ2 账本字段能否让人快速定位错误
RQ3 BO 是否在保持审计覆盖的同时降低 review burden
```

---

## 8. 实施阶段

### P0 计划与 schema

```text
[x] 账本 schema
[x] review_priority 规则
[ ] 人类动作定义
```

### P1 账本生成

```text
[x] 从 evidence bundle 生成账本（纯 builder）
[x] claim -> citation -> sentence 连接
[x] 缺失/未知 citation 标记
[x] QA 结果可选附加 ledger
```

### P2 审核界面

```text
[x] 按 review_priority 排序
[x] 展开句子/文章/得分
[x] accept / add_evidence / remove_claim
[x] 审计日志（append-only action log）
[x] 动作生成新账本版本（不改旧版）
[x] error lifecycle（detected -> closed / unresolved）
[x] 账本页面 error 队列 + transition
[x] closed 闸门：revision + 服务端 verification + diff
[x] revision 自动生成 repaired error
[x] 证据约束重写服务 + HTTP 路由
[x] UI：勾选证据 -> draft -> 接受新版本
[x] 决策表：unit_role / AnswerVersion / per-answer chain / outbox
```

### P3 BO 离线实验

```text
[ ] 固定审计覆盖
[ ] 比较 review_burden
[ ] 不自动接基座
```

---

## 9. 不做

```text
不做领域标注
不做 anchor_type 标注
不做 query_type 人工分层
不因为 recall 高就跳过账本
不让 BO 改审计字段
```

---

## 10. 范围控制、入库与快照

科研人员可以指定：

```text
paper_ids / collection
时间范围
section 类型
纳入 / 排除
指定句子或段落
```

也可以：

```text
上传缺失论文
填 DOI/PMID
加入指定 collection
重新解析/索引
```

然后：

```text
按新范围重新检索
生成新版本
对比旧版本
```

### 10.1 数据库“活”了，但必须可复现

每次检索记录：

```text
corpus_snapshot_id
scope
added_paper_ids
excluded_paper_ids
indexed_at
```

规则：

```text
新论文入库 -> 新 snapshot
旧回答仍绑定旧 snapshot
重跑 -> 新 answer_id + 新 snapshot
```

不能：

```text
入库后静默改变旧回答的引用
不记录 scope
不记录 snapshot
```

### 10.2 人类补充文献

```text
发现缺某篇
  -> 上传/填 DOI
  -> 解析
  -> 入库
  -> 新 snapshot
  -> 限定该篇/该 collection 重跑
  -> 新旧证据对比
```

### 10.3 范围偏置

限定范围会改变结论：

```text
只选支持某观点的论文
只选某时间段
只选某期刊
```

所以必须记录：

```text
scope
selection_reason
actor
```

审计时能看到“结论是在什么范围内得出的”。

---

## 11. 错误闭环

发现问题不是终点。每条错误必须有状态和动作：

```text
detected
  -> triaged
  -> repair_proposed
  -> repaired
  -> verified
  -> closed
```

或：

```text
unresolved（当前语料无法解决）
```

### 11.1 错误记录

```text
error_id
answer_id
claim_id
evidence_id
error_type
severity
detected_by
status
owner
created_at
```

### 11.2 修复动作

```text
re_retrieve       重新检索
expand_scope      扩大范围
add_paper         补文献
exclude_source    排除来源
reject_citation   打回引用
rewrite_claim     重写 claim
rewrite_paragraph 重写段落
re_verify         重新验证
```

### 11.3 AI 的角色

```text
定位：claim -> evidence -> source
提议：候选修复动作
执行：重检索/重写
验证：citation / claim / provenance
```

人：

```text
判断错误是否真实
选择修复动作
接受/拒绝新版本
```

### 11.4 关闭条件

不能只点“已读”。关闭必须满足：

```text
有新版本或明确 unresolved
新版本有 claim -> evidence
verification 重新跑过
diff 可见
审计日志完整
```

### 11.5 错误变成回归测试

人工修复后：

```text
把该 case 加入 regression set
记录预期证据/结论
下次版本必须通过
```

这不是自动训练，是**审计驱动的回归**。

### 11.6 不允许

```text
错误标记为已读但没有动作
修复后不重跑验证
新版本覆盖旧版本
unresolved 被隐藏
人工修复静默变成模型训练
```

---

## 12. 一句话

```text
审计不是“给问题分类”
审计是“把每条证据和每条 claim 摊开给人看”
BO 只是让摊开的东西少一点，不是把账本合上
```
