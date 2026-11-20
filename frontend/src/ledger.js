const errorBox = document.getElementById("error");
const listBox = document.getElementById("list");
const errorsBox = document.getElementById("errors");
const detailBox = document.getElementById("detail");
const draftBox = document.getElementById("draft");

const NEXT_STATUS = {
  detected: ["triaged", "unresolved"],
  triaged: ["repair_proposed", "unresolved"],
  repair_proposed: ["repaired", "unresolved"],
  repaired: ["verified", "unresolved"],
  verified: ["closed", "unresolved"],
  unresolved: ["triaged"],
};

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `请求失败 (${response.status})`);
  return body;
}

function el(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

function table(headers, rows) {
  const node = document.createElement("table");
  const head = document.createElement("tr");
  for (const header of headers) head.appendChild(el("th", header));
  node.appendChild(head);
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const cell of row) {
      const td = document.createElement("td");
      if (cell instanceof Node) td.appendChild(cell);
      else td.textContent = cell ?? "";
      tr.appendChild(td);
    }
    node.appendChild(tr);
  }
  return node;
}

function answerLink(answerId, text) {
  const link = el("a", text || answerId);
  link.href = "#";
  link.addEventListener("click", (event) => {
    event.preventDefault();
    loadDetail(answerId);
  });
  return link;
}

async function loadList() {
  listBox.replaceChildren();
  const body = await api("/api/audit/ledgers?limit=100");
  if (!body.ledgers.length) {
    listBox.appendChild(el("div", "empty", "还没有账本。先跑一次 QA，并开启 SCIPAL_EVIDENCE_LEDGER=on。"));
    return;
  }
  listBox.appendChild(
    table(
      ["时间", "answer_id", "query", "证据", "高优先", "config", "snapshot"],
      body.ledgers.map((row) => {
        const summary = row.summary || {};
        return [
          row.created_at,
          answerLink(row.answer_id),
          row.query,
          summary.evidence ?? "",
          summary.high_priority ?? "",
          row.config_id,
          row.corpus_snapshot_id,
        ];
      })
    )
  );
}

async function loadDetail(answerId) {
  detailBox.replaceChildren();
  const ledger = await api(`/api/audit/ledgers/${encodeURIComponent(answerId)}`);
  detailBox.appendChild(el("div", "hint", `${ledger.query} · ${ledger.answer_id}`));
  const summary = ledger.summary || {};
  detailBox.appendChild(
    table(
      ["claims", "uncited", "unknown", "evidence", "cited", "high"],
      [[summary.claims ?? 0, summary.uncited_claims ?? 0, summary.unknown_evidence_claims ?? 0, summary.evidence ?? 0, summary.cited_evidence ?? 0, summary.high_priority ?? 0]]
    )
  );

  const claims = ledger.claims || [];
  if (claims.length) {
    detailBox.appendChild(el("h2", "Claims"));
    detailBox.appendChild(
      table(
        ["status", "claim", "cited sentence ids", "操作"],
        claims.map((claim) => [
          claim.support_status,
          claim.text,
          (claim.cited_sentence_ids || []).join(", "),
          claimActions(ledger.answer_id, claim.claim_id),
        ])
      )
    );
  }

  detailBox.appendChild(el("h2", "Evidence"));
  const evidenceTable = table(
    ["选", "priority", "cited", "score", "sentence", "paper", "section / page", "text", "操作"],
    (ledger.evidence || []).map((item) => {
      const priority = el("span", item.review_priority);
      priority.className = `badge ${item.review_priority}`;
      const checkbox = el("input");
      checkbox.type = "checkbox";
      checkbox.className = "evidence-select";
      checkbox.value = item.sentence_id;
      return [
        checkbox,
        priority,
        item.cited ? "yes" : "no",
        item.rerank_score ?? item.retrieval_score ?? "",
        item.sentence_id,
        item.title || item.paper_id,
        `${item.section || ""} / ${item.page ?? ""}`,
        item.text,
        actionButton("accept", () => postAction(ledger.answer_id, { action: "accept", target_id: item.sentence_id })),
      ];
    })
  );
  const evidenceRows = evidenceTable.querySelectorAll("tr");
  (ledger.evidence || []).forEach((item, index) => {
    if (item.review_priority === "high") evidenceRows[index + 1]?.classList.add("high");
  });
  detailBox.appendChild(evidenceTable);

  const actions = (await api(`/api/audit/ledgers/${encodeURIComponent(ledger.answer_id)}/actions`)).actions || [];
  if (actions.length) {
    detailBox.appendChild(el("h2", "Review actions"));
    detailBox.appendChild(
      table(
        ["时间", "actor", "action", "target", "note"],
        actions.map((row) => [row.created_at, row.actor, row.action, row.target_id, row.note])
      )
    );
  }
}

function actionButton(label, onClick) {
  const button = el("button", label);
  button.style.marginRight = "6px";
  button.addEventListener("click", onClick);
  return button;
}

function claimActions(answerId, claimId) {
  const box = el("span");
  box.appendChild(actionButton("accept", () => postAction(answerId, { action: "accept", target_id: claimId })));
  box.appendChild(actionButton("rewrite", () => rewriteClaim(answerId, claimId)));
  box.appendChild(actionButton("remove_claim", () => postRevision(answerId, { action: "remove_claim", target_id: claimId })));
  box.appendChild(actionButton("flag_missing", () => postRevision(answerId, { action: "flag_missing", target_id: claimId })));
  box.appendChild(actionButton("add_evidence", async () => {
    const sentenceId = window.prompt("要补充的 sentence_id");
    if (!sentenceId) return;
    const paperId = window.prompt("paper_id（可空）") || "";
    const text = window.prompt("证据文本（可空）") || "";
    await postRevision(answerId, {
      action: "add_evidence",
      target_id: claimId,
      evidence: { sentence_id: sentenceId, paper_id: paperId, text },
    });
  }));
  return box;
}

async function rewriteClaim(answerId, claimId) {
  const ids = [...document.querySelectorAll(".evidence-select:checked")].map((node) => node.value);
  if (!ids.length) {
    window.alert("先勾选要作为依据的证据");
    return;
  }
  const result = await api(`/api/audit/ledgers/${encodeURIComponent(answerId)}/rewrite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ claim_id: claimId, evidence_ids: ids }),
  });
  draftBox.replaceChildren();
  if (result.status === "rejected") {
    draftBox.appendChild(el("div", "empty", `重写被拒绝：${result.reason || ""}`));
    return;
  }
  const pre = el("pre", result.draft);
  draftBox.appendChild(pre);
  draftBox.appendChild(actionButton("接受并生成新版本", async () => {
    await postRevision(answerId, {
      action: "rewrite_claim",
      target_id: claimId,
      new_text: result.draft,
      evidence_ids: result.used_sentence_ids || ids,
    });
    draftBox.replaceChildren();
  }));
  draftBox.appendChild(actionButton("丢弃", () => draftBox.replaceChildren()));
}

async function postRevision(answerId, body) {
  const result = await api(`/api/audit/ledgers/${encodeURIComponent(answerId)}/revisions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await loadErrors();
  if (result.ledger?.answer_id) await loadDetail(result.ledger.answer_id);
}

async function postAction(answerId, body) {
  await api(`/api/audit/ledgers/${encodeURIComponent(answerId)}/actions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await loadDetail(answerId);
}

async function loadErrors() {
  errorsBox.replaceChildren();
  const body = await api("/api/audit/errors?limit=100");
  if (!body.errors.length) {
    errorsBox.appendChild(el("div", "empty", "还没有错误记录。"));
    return;
  }
  errorsBox.appendChild(
    table(
      ["updated", "answer", "type", "status", "target", "操作"],
      body.errors.map((row) => [
        row.updated_at,
        answerLink(row.answer_id),
        row.error_type,
        row.status,
        row.target_id,
        errorActions(row.error_id, row.status),
      ])
    )
  );
}

function errorActions(errorId, status) {
  const box = el("span");
  for (const next of NEXT_STATUS[status] || []) {
    if (next === "closed") {
      box.appendChild(actionButton(next, () => closeError(errorId)));
      continue;
    }
    box.appendChild(actionButton(next, async () => {
      await api(`/api/audit/errors/${encodeURIComponent(errorId)}/transition`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: next }),
      });
      await loadErrors();
    }));
  }
  return box;
}

async function closeError(errorId) {
  const revisionAnswerId = window.prompt("新版本 answer_id");
  if (!revisionAnswerId) return;
  try {
    await api(`/api/audit/errors/${encodeURIComponent(errorId)}/transition`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: "closed",
        revision_answer_id: revisionAnswerId,
      }),
    });
    await loadErrors();
  } catch (error) {
    window.alert(error.message);
  }
}

async function load() {
  errorBox.textContent = "";
  try {
    await Promise.all([loadList(), loadErrors()]);
  } catch (error) {
    if (String(error.message).includes("401")) {
      window.location.replace("/login.html");
      return;
    }
    errorBox.textContent = error.message;
  }
}

load();
