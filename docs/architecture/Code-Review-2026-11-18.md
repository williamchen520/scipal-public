# 代码审查：审计账本与 outbox

> 日期：2026-11-18  
> 范围：审计账本、PG 存储、outbox/worker、证据约束重写、关闭闸门  
> 性质：聚焦审查，不是完整安全审计

---

## 1. 审查范围

```text
services/audit/evidence_ledger.py
services/audit/ledger_revision.py
services/audit/ledger_verification.py
services/audit/error_lifecycle.py
services/audit/outbox.py
services/audit/regen_handler.py
services/audit/pg_store.py
routes/ledger.py
scripts/audit_outbox_worker.py
deploy/sql/055_audit_ledger.sql
deploy/sql/056_audit_outbox_idempotency.sql
```

---

## 2. 已修复

### CR-1 HIGH：worker 在可重试时错误标 unresolved

问题：

```text
worker 捕获异常后
先 transition error -> unresolved
再 fail outbox -> 可能 pending
```

结果：

```text
error 已 unresolved
job 还会 retry
状态矛盾
```

修复：

```text
先 fail()
只有 fail 返回 unresolved 才 transition error
```

### CR-2 HIGH：remove_claim 被误做成 rewrite_claim

问题：

```text
用户明确 remove_claim
worker 却调用 LLM 重写该 claim
```

修复：

```text
remove_claim -> 结构化删除该 claim
不调用 LLM
删除后 verify；失败 -> unresolved
```

### CR-3 MEDIUM：reject 未校验 target claim

问题：

```text
remove_claim/flag_missing 可以指向不存在 claim
仍创建 error + outbox
worker 之后才失败
```

修复：

```text
写 error/outbox 前校验 claim 存在
不存在 -> 404
```

---

## 3. 未修复风险

### CR-4 MEDIUM：outbox 幂等键不是请求幂等

现状：

```text
idempotency_key = action_id
action_id 每次新生成
```

结果：

```text
用户重复点击 remove_claim
可能产生多条 outbox
```

建议：

```text
Idempotency-Key header
或 answer_id + action + target_id 的稳定 key
```

注意：

```text
稳定 key 会阻止“失败后同一操作重试”
需要配合显式 retry flag
```

### CR-5 LOW：metrics 出现 unknown action

原因：

```text
历史 audit_event payload 形状不一致
```

影响：

```text
只影响 actions_by_type
不影响审计结论
```

建议：

```text
迁移历史 payload
或 metrics 统一解析 action.action
```

### CR-6 MEDIUM：source_ref.version 可空

现状：

```text
build_ledger 在 corpus_snapshot_id 为空时
仍写入 source_ref.version = ""
```

契约校验会报错，但构建不强制。

建议：

```text
无 snapshot -> 拒绝生成正式 ledger
或标记 draft，不允许 close
```

### CR-7 MEDIUM：worker 无并发上限/运行监控

现状：

```text
--once 单次领取
无常驻 worker 健康指标
```

影响：

```text
生产部署需要 cron/进程管理
```

建议：

```text
systemd/compose worker
metrics: pending/running/unresolved
```

---

## 3.1 CR-8 测试套件不可容器化全量运行

现象：

```text
release image 内跑全量 unittest
大量 SQLite 备份/路径 fixture 失败
```

原因：

```text
测试依赖 host fixture
测试需要 SCIPAL_SQLITE_RUNTIME=1
生产 env 关闭 SQLite
```

处理：

```text
发布验证用 clean host worktree
容器只跑服务 smoke
不把容器全量测试写成通过
```

---

## 4. 安全边界

```text
worker 是本地脚本，不是公网端点
审计表 append-only 触发器已建
关闭验证在服务端
重写只允许选中证据
```

未覆盖：

```text
完整渗透测试
PG 角色权限最小化
依赖供应链扫描
```

---

## 5. 回归

```text
20 audit/revision/route tests OK
```

---

## 6. 结论

```text
没有发现会绕过关闭闸门的新问题
发现并修复了 3 个状态/语义问题
剩余风险主要是幂等、数据质量和部署运维
```
