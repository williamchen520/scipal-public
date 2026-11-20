# 路由与数据流（含人的位置）

> 日期：2026-11-18  
> 范围：manuscript-polish skill + SciPal 审计基座  
> 原则：任务拆解、单任务单 owner、人负责判断、系统负责证据链

---

## 1. 总体路由

```mermaid
flowchart TB
    H1["作者 / 科研人员<br/>定范围 · 选证据 · 接受/拒绝"]
    H2["审稿人 / 审计者<br/>复核 claim · 关闭错误"]

    subgraph SKILL["manuscript-polish skill（本地）"]
        S1["解析 / 分段"]
        S2["保护 span"]
        S3["确定性检测"]
        S4{"任务路由"}
        S5["建议 + diff"]
        S6["checker"]
    end

    subgraph MODEL["本地模型"]
        M1["4B / 7B 小模型<br/>只改拗口句"]
        M2["无模型回退<br/>deterministic only"]
    end

    subgraph CORE["SciPal 基座"]
        C1["检索 / 证据"]
        C2["Evidence Ledger"]
        C3["Error / Outbox / Worker"]
        C4["Verification / Diff"]
    end

    H1 -->|section / 目标| S1
    S1 --> S2 --> S3 --> S4
    S4 -->|机械问题| S5
    S4 -->|清晰度| M1 --> S5
    S4 -->|无 GPU| M2 --> S5
    S4 -->|claim / citation| C1
    C1 --> C2
    S5 --> S6
    S6 -->|pass| H1
    S6 -->|fail| S5
    H1 -->|accept| PATCH["新 manuscript 版本"]
    H1 -->|reject| S4
    C2 --> H2
    H2 -->|reject / 选证据| C3
    C3 -->|新 ledger| C4
    C4 --> H2
    H2 -->|verified / closed| C4
```

人不是外部观察者：

```text
作者：定范围、接受/拒绝语言建议
审计者：判断 claim/evidence、决定错误是否关闭
```

---

## 2. 润色 skill 的路由

```mermaid
flowchart LR
    IN["manuscript section"] --> SEG["segments<br/>paragraph / sentence id"]
    SEG --> PROT["protected spans<br/>citation · number · unit · hedge · entity"]
    PROT --> DET["deterministic detectors<br/>LanguageTool · Vale · Harper · codespell"]
    DET --> R{"route"}
    R -->|spelling / grammar / punctuation| SUG["suggestion"]
    R -->|style / long sentence| LM["local 4B/7B<br/>minimal edit"]
    R -->|claim / citation conflict| EVID["SciPal evidence"]
    R -->|argument / narrative| HUMAN["human rewrite"]
    LM --> SUG
    SUG --> CHECK["manuscript_polish_check"]
    CHECK -->|pass| DIFF["diff + edit log"]
    CHECK -->|fail| REVERT["revert paragraph"]
    DIFF --> HUMAN2["author accept / reject"]
    HUMAN2 -->|accept| VERSION["new manuscript version"]
    HUMAN2 -->|reject| R
```

单任务单 owner：

| 任务 | owner | 是否 GPU | 人是否必须 |
|---|---|---|---|
| 拼写/语法/标点 | LanguageTool | 否 | 接受建议 |
| 学术 style | Vale | 否 | 接受建议 |
| 英文 grammar | Harper | 否 | 接受建议 |
| citation/number 保护 | checker | 否 | 失败即拒绝 |
| 拗口句 | 4B/7B | 是 | 接受建议 |
| 论证 | 人 | 否 | 是 |
| claim/citation 核查 | SciPal | 否 | 是 |

---

## 3. 润色数据流

```mermaid
flowchart TB
    MS["manuscript version vN"] --> SEG["segments"]
    SEG --> RUN["polish_run"]
    RUN --> ISSUES["issues"]
    RUN --> SUG["suggestions"]
    SUG --> CHECK["checker"]
    CHECK --> PATCH["accepted patch"]
    PATCH --> MS2["manuscript version vN+1"]
    CHECK -->|fail| RISK["risk report"]
    RISK --> HUMAN["author decision"]
    HUMAN -->|fix manually| MS2
    HUMAN -->|reject| RUN
```

数据边界：

```text
manuscript store
  manuscript / section / paragraph / version

polish_run
  issues / suggestions / diff / checker result

evidence ledger
  claim / evidence / action / error / outbox
```

规则：

```text
润色数据不进 evidence ledger
证据数据不塞进 manuscript store
```

---

## 4. 证据审计数据流

```mermaid
flowchart LR
    CLAIM["manuscript claim"] --> Q["SciPal retrieval"]
    Q --> EV["evidence candidates"]
    EV --> LEDGER["evidence ledger<br/>claim -> evidence"]
    LEDGER --> HUMAN["researcher / auditor"]
    HUMAN -->|accept| VERIFY["verify_ledger"]
    HUMAN -->|reject| OUTBOX["outbox"]
    OUTBOX --> WORKER["worker"]
    WORKER --> REWRITE["evidence-constrained rewrite"]
    REWRITE --> LEDGER2["new ledger version"]
    LEDGER2 --> VERIFY
    VERIFY -->|ok| CLOSE["closed"]
    VERIFY -->|fail| UNRESOLVED["unresolved"]
```

人的作用：

```text
选择证据范围
判断 claim 是否成立
接受/拒绝新版本
决定 unresolved 还是继续
```

系统的作用：

```text
找回候选
记录 provenance
生成新版本
服务端验证
保存 diff / 哈希链
```

---

## 5. 人机时序：润色

```mermaid
sequenceDiagram
    actor A as Author
    participant S as Skill
    participant D as Deterministic tools
    participant L as Local model
    participant C as Checker
    participant M as Manuscript store

    A->>S: polish section
    S->>D: grammar/style check
    D-->>S: issues
    S->>S: route by task
    opt clarity
        S->>L: rewrite flagged sentence
        L-->>S: draft + used spans
    end
    S->>C: citations/numbers/hedges
    alt check pass
        C-->>S: pass
        S-->>A: diff + edit log
        A->>S: accept
        S->>M: new version
    else check fail
        C-->>S: fail
        S-->>A: risk + revert
    end
```

---

## 6. 人机时序：证据审计

```mermaid
sequenceDiagram
    actor A as Researcher
    participant API as SciPal API
    participant DB as PostgreSQL
    participant W as Worker

    A->>API: reject claim / select evidence
    API->>DB: action + error + outbox (same tx)
    API-->>A: pending
    W->>DB: claim job SKIP LOCKED
    W->>API: evidence-constrained rewrite
    API->>DB: new ledger version
    W->>DB: error repaired
    A->>API: verified -> closed
    API->>DB: server verify + diff
    API-->>A: closed / rejected
```

---

## 7. 人的位置

| 阶段 | 人做什么 | 系统做什么 |
|---|---|---|
| 开始 | 选 section、目标期刊、范围 | 解析、保护 span |
| 润色 | 接受/拒绝建议 | 检测、路由、checker |
| 证据 | 判断 claim 是否成立 | 检索、账本、provenance |
| 修复 | 选证据、打回、补文献 | outbox、重写、新版本 |
| 关闭 | 确认 verified | 服务端验证、diff、哈希链 |
| 发布 | 承担最终责任 | 保存可复现 artifact |

不可让渡：

```text
科学判断
价值判断
最终署名责任
```

---

## 8. 降级与失败

```text
无 GPU
  -> deterministic only
  -> 不偷偷切云端

checker fail
  -> 拒绝该段
  -> 不自动写回

citation 不存在
  -> 转 evidence 流程
  -> 不在润色里“顺手改”

模型越界
  -> 拒绝 draft
  -> 记录 unresolved
```

---

## 9. 一句话

```text
润色是作者平面
证据审计是证据平面
人在两个平面都负责判断
系统只负责让判断可追溯、可验证、可复现
```
