# 证据账本 Schema v1

> 日期：2026-11-18  
> 状态：P0/P1，纯 builder，未接 UI  
> 代码：`services/audit/evidence_ledger.py`

---

## 1. 输入

```text
query
answer
evidence[]
claims[]
corpus_snapshot_id
scope
config_id
```

`evidence[]`：

```text
sentence_id
paper_id
para_id
title
section
page
text
retrieval_score
rerank_score
rank
```

`claims[]`：

```text
claim_id
text
cited_sentence_ids
```

---

## 2. 输出

```text
schema_version
answer_id
created_at
query
answer
config_id
corpus_snapshot_id
scope
claims[]
evidence[]
summary
```

`claims[]` 状态：

```text
cited             引用都存在于 evidence
uncited           没有引用
unknown_evidence  引用了不存在的句子
```

`evidence[]` 状态：

```text
cited
review_priority: low | medium | high
```

---

## 3. review_priority

```text
high:
  cited 但 provenance 不完整
  cited 但 score < 0.3
  uncited 但 score >= 0.8
  provenance 不完整

medium:
  uncited 但 score >= 0.5

low:
  其余
```

规则是策略，不是科学结论；后续可调，但必须留版本。

---

## 4. summary

```text
claims
uncited_claims
unknown_evidence_claims
evidence
cited_evidence
high_priority
```

---

## 5. 版本与范围

账本必须绑定：

```text
config_id
corpus_snapshot_id
scope
```

数据库新增论文：

```text
新 snapshot
旧账本不重写
重跑生成新 answer_id
```

---

## 6. QA 接入

```text
SCIPAL_EVIDENCE_LEDGER=on
```

QAService 在答案结果里追加：

```text
result["ledger"]
```

来源：

```text
retrieval_result.paragraphs
claim_audit.claims
```

仍未做：

```text
没有 UI
没有 review action 持久化
没有 error lifecycle
没有 BO 对照
```

---

## 7. 一句话

```text
账本不是给 query 打分
账本是把 claim、句子、文章、得分、引用状态摊开
```

## 8. API / UI

```text
GET /api/audit/ledgers?limit=100
GET /api/audit/ledgers/<answer_id>
frontend/ledger.html
```

页面：

```text
账本列表
claim / evidence
high priority 高亮
sentence / paper / section / page / score
```

实测：

```text
QA ledger saved
answer_id = ans_b9c05f549432
snapshot = corpus-2026-11-18
claims 7
evidence 10
uncited_claims 1
```

仍未做：

```text
accept / add_evidence / remove_claim
review action 持久化
error lifecycle
```

## 9. Review actions

```text
GET  /api/audit/ledgers/<id>/actions
POST /api/audit/ledgers/<id>/actions
     {"action":"accept|add_evidence|remove_claim|flag_missing",
      "target_id":"...", "note":"..."}
```

存储：

```text
logs/ledger-review-actions.jsonl
SCIPAL_LEDGER_ACTIONS_PATH
```

规则：

```text
append-only
不改写原账本
actor 来自 session
```

UI：

```text
claim: accept / remove_claim / flag_missing / add_evidence
evidence: accept
```

## 10. New ledger version

```text
POST /api/audit/ledgers/<answer_id>/revisions
     {"action":"remove_claim|add_evidence|flag_missing",
      "target_id":"...", "note":"...", "evidence":{...}}
```

规则：

```text
不修改旧账本
新 answer_id
parent_answer_id
revision = old + 1
source_action
```

`add_evidence` 需要：

```text
sentence_id / paper_id / text
```

`flag_missing` 写入：

```text
unresolved[]
```

返回：

```json
{"ledger": {...}, "error": {"status": "repaired", "revision_answer_id": "ans_..."}}
```

`error` 自动进入 `repaired`，关闭时可直接绑定该版本。

## 11. Error lifecycle

```text
GET  /api/audit/errors
POST /api/audit/errors
POST /api/audit/errors/<error_id>/transition
```

状态：

```text
detected -> triaged -> repair_proposed -> repaired -> verified -> closed
unresolved
```

触发：

```text
remove_claim / flag_missing
  -> 自动创建 error
```

存储：

```text
logs/audit-errors.jsonl
SCIPAL_ERRORS_PATH
```

关闭条件仍是：

```text
新版本 + 验证 + diff + 日志
```

## 12. Close gate

`verified -> closed` 必须带：

```json
{
  "status": "closed",
  "revision_answer_id": "ans_...",
  "verification_ok": true,
  "diff": "..."
}
```

API 额外检查：

```text
revision ledger exists
revision.parent_answer_id == error.answer_id
verify_ledger(revision).ok
diff_ledgers(parent, revision)
```

客户端不再传 `verification_ok` / `diff`，服务端计算。

验证失败示例：

```text
no_claims
uncited
unknown_evidence
provenance
```

缺任一项：

```text
400
```

## 13. 完整链路实测（2026-11-18）

```text
start ledger      ans_47185a901869
remove_claim
  -> new ledger   ans_1e24b3e30388
  -> parent       ans_47185a901869
  -> error        err_aefbf1867162
  -> status       repaired

verified
  -> closed 200
  -> revision_answer_id ans_1e24b3e30388
```

验证：

```text
GET /api/audit/ledgers/<new>  200
error status                  closed
```

结论：

```text
发现 -> 修复 -> 验证 -> 关闭 已闭环
```

边界：

```text
remove_claim 是结构删除
不是 LLM 重写
重写仍需后续接入 rewrite
```

## 14. Event hash chain

```text
GET /api/audit/ledgers/<answer_id>/chain
```

每条 answer 链：

```text
chain_id
prev_event_hash
event_hash
```

写入：

```text
action
revision
```

校验：

```text
SHA256(prev_event_hash + canonical_json(event))
```

篡改任一条：

```text
verification.ok=false
```

## 15. PostgreSQL 存储（Q5 phase 1）

迁移：

```text
deploy/sql/055_audit_ledger.sql
```

表：

```text
audit_ledger
audit_event
audit_error
audit_error_event
audit_outbox
```

当前切换：

```text
SCIPAL_AUDIT_PG=1
  -> ledger save/list/get 走 audit_ledger
```

已切换：

```text
ledger save/list/get
actions record/list
errors create/get/transition/list
event chain append/verify
```

尚未切换：

```text
outbox worker
workspace Merkle anchor
PG 权限角色分离
```

验证：

```text
action accept -> PG
error detected -> triaged -> PG
chain verify ok=True
```

## 16. Outbox（Q4）

原子写：

```text
remove_claim / flag_missing
  -> audit_event
  -> audit_error / audit_error_event
  -> audit_outbox(pending)
同一事务
```

worker：

```text
scripts/audit_outbox_worker.py --once
SELECT ... FOR UPDATE SKIP LOCKED
```

当前：

```text
enqueue 原子
claim 可用
regen handler 已接
  -> evidence rewrite
  -> 新 ledger
  -> error repaired

验证闸门：
  worker 先生成新 ledger
  -> verify_ledger
  -> 不通过 -> unresolved
  -> 通过 -> save + repaired

幂等：
  error 已 repaired
  -> already_repaired
  -> worker 标 done
```

可靠性：

```text
stale running -> pending
attempts >= max_attempts -> unresolved
worker --max-attempts / --stale-seconds
```

仍缺：

```text
workspace Merkle anchor
PG 权限角色分离
```

不假装：

```text
没有 handler 就不写 accepted
不自动关闭 error
```

## 17. Worker 实测（2026-11-18）

```text
outbox 5 pending
worker --once
  -> new ledger ans_be3fc6614dda
  -> error repaired
  -> outbox done attempts=1
```

说明：

```text
真实 LLM 重写已接
不是 mock
```
