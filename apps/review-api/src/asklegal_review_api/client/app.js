// Local Review client. The bearer value exists only in this module's memory.
let accessToken = null;
let selectedProposal = null;
let pendingDecision = null;

const tokenInput = document.querySelector("#review-token");
const connectButton = document.querySelector("#connect");
const disconnectButton = document.querySelector("#disconnect");
const refreshButton = document.querySelector("#refresh");
const session = document.querySelector("#session");
const proposals = document.querySelector("#proposals");
const proposalSummary = document.querySelector("#proposal-summary");
const proposalDetail = document.querySelector("#proposal-detail");
const reasonInput = document.querySelector("#decision-reason");
const approveButton = document.querySelector("#approve");
const rejectButton = document.querySelector("#reject");
const decisionResult = document.querySelector("#decision-result");

const scopeLabels = {
  "HK-CASE-BINDING-POST-1997": "Binding-court case propositions",
  "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS": "Constitutional and other instruments",
  "HK-LEG-ORDINANCES": "Ordinances",
  "HK-LEG-SUBSIDIARY": "Subsidiary legislation",
};

function commandId() {
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  return `cmd_${Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("")}`;
}

function authorizationHeaders() {
  if (accessToken === null) throw new Error("Connect before making a Review request.");
  return {Authorization: `Bearer ${accessToken}`};
}

async function responseBody(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return response.json();
  return {message: await response.text()};
}

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {...authorizationHeaders(), ...(options.headers || {})},
    credentials: "omit",
  });
  const body = await responseBody(response);
  if (!response.ok) {
    const code = body.error_code || body.message || `HTTP ${response.status}`;
    throw new Error(String(code));
  }
  return {body, etag: response.headers.get("etag")};
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function readable(value) {
  return String(value || "Unknown").replaceAll("_", " ").toLowerCase()
    .replace(/^./, (letter) => letter.toUpperCase());
}

function shortFingerprint(value) {
  const text = String(value || "Unavailable");
  return text.length > 25 ? `${text.slice(0, 16)}…${text.slice(-8)}` : text;
}

function setStage(name, state, text) {
  const stage = document.querySelector(`[data-stage="${name}"]`);
  stage.dataset.state = state;
  stage.querySelector(".stage-state").textContent = text;
}

function updatePipelineStages(detail = null) {
  if (detail === null) {
    setStage("source", "idle", "Waiting for demo input");
    setStage("evidence", "idle", "Waiting");
    setStage("processing", "idle", "Waiting");
    setStage("review", accessToken === null ? "attention" : "idle", accessToken === null ? "Connect to inspect" : "Waiting for proposal");
    setStage("promotion", "idle", "Not started");
    return;
  }
  setStage("source", "ready", "Synthetic change prepared");
  setStage("evidence", "ready", "Preserved locally");
  setStage("processing", "ready", "Package verified");
  if (detail.decision === null) {
    setStage("review", "attention", "Awaiting your decision");
    setStage("promotion", "idle", "Blocked by review");
  } else if (detail.decision.decision === "APPROVED") {
    setStage("review", "ready", "Proposal approved");
    setStage("promotion", "attention", "Queued for local demo");
  } else {
    setStage("review", "stopped", "Proposal rejected");
    setStage("promotion", "stopped", "Stopped by reviewer");
  }
}

function metric(label, value) {
  const item = node("div", "metric");
  item.append(node("span", "", label), node("strong", "", value));
  return item;
}

function renderProposalDetail(detail) {
  const readiness = detail.hk_v1_readiness;
  const heading = node("div", "proposal-heading");
  const title = node("div");
  title.append(
    node("h3", "", detail.proposal.title),
    node("p", "", `Frozen at ${detail.observation_cutoff}`),
  );
  heading.append(title, node("span", "badge", readable(detail.proposal.status)));

  const metrics = node("div", "metric-grid");
  metrics.append(
    metric("Scopes", String(readiness?.scope_dispositions?.length || 0)),
    metric("Target records", String(readiness?.target_members?.length || 0)),
    metric("Package members", String(detail.artifacts.length)),
    metric("Review version", String(detail.proposal.review_version)),
  );

  const summaryGrid = node("div", "summary-grid");
  const scopes = node("section", "summary-block");
  scopes.append(node("h3", "", "Coverage decision"));
  const scopeList = node("ul", "scope-list");
  for (const scope of readiness?.scope_dispositions || []) {
    const item = node("li");
    item.append(
      node("span", "", scopeLabels[scope.scope_id] || scope.scope_id),
      node("span", "scope-result", readable(scope.result)),
    );
    scopeList.append(item);
  }
  scopes.append(scopeList);

  const limits = node("section", "summary-block");
  limits.append(node("h3", "", "POC boundaries"));
  const limitationList = node("ul", "limitations");
  for (const limitation of readiness?.limitations || []) {
    limitationList.append(node("li", "", limitation));
  }
  limits.append(limitationList);
  summaryGrid.append(scopes, limits);

  const technical = node("p", "proposal-meta", `Package ${shortFingerprint(detail.package_fingerprint)} · target ${readiness?.target_name || "local fake"}`);
  proposalSummary.replaceChildren(heading, metrics, summaryGrid, technical);
  proposalDetail.textContent = JSON.stringify(detail, null, 2);
  updatePipelineStages(detail);
}

function clearSelection() {
  selectedProposal = null;
  pendingDecision = null;
  proposalSummary.replaceChildren(node("p", "empty", "Select a proposal to inspect its complete package."));
  proposalDetail.textContent = "No proposal selected.";
  reasonInput.value = "";
  reasonInput.disabled = true;
  approveButton.disabled = true;
  rejectButton.disabled = true;
  decisionResult.textContent = "";
  updatePipelineStages();
}

async function selectProposal(proposalId) {
  clearSelection();
  proposalSummary.replaceChildren(node("p", "empty", "Loading proposal package…"));
  try {
    const result = await requestJson(`/api/v1/proposal-packages/${encodeURIComponent(proposalId)}`);
    if (result.etag === null) throw new Error("The proposal version was not supplied.");
    selectedProposal = {
      id: proposalId,
      etag: result.etag,
      manifestFingerprint: result.body.proposal.manifest_fingerprint,
    };
    renderProposalDetail(result.body);
    const decisionOpen = result.body.decision === null;
    reasonInput.disabled = !decisionOpen;
    approveButton.disabled = !decisionOpen;
    rejectButton.disabled = !decisionOpen;
    if (!decisionOpen) {
      decisionResult.textContent = `${readable(result.body.decision.decision)} by ${result.body.decision.reviewer_identity_id}: ${result.body.decision.reason}`;
    }
  } catch (error) {
    proposalSummary.replaceChildren(node("p", "empty", `Unable to load proposal: ${error.message}`));
  }
}

function proposalListItem(item) {
  const button = node("button", "proposal-button");
  button.type = "button";
  button.append(
    node("span", "proposal-title", item.title),
    node("span", "proposal-meta", `${readable(item.status)} · ${shortFingerprint(item.manifest_fingerprint)}`),
  );
  button.addEventListener("click", () => void selectProposal(item.proposal_id));
  const listItem = node("li");
  listItem.append(button);
  return listItem;
}

async function loadProposals(preferredProposalId = null) {
  if (accessToken === null) return;
  session.textContent = "Loading Review proposals…";
  try {
    const result = await requestJson("/api/v1/proposal-packages");
    const items = result.body.items;
    if (items.length === 0) {
      proposals.replaceChildren(node("li", "empty", "No review-ready proposal is available yet."));
      clearSelection();
      session.textContent = "Connected. Waiting for a prepared synthetic proposal.";
      return;
    }
    proposals.replaceChildren(...items.map(proposalListItem));
    session.textContent = "Connected to the local Review service.";
    const preferred = items.find((item) => item.proposal_id === preferredProposalId) || items[0];
    await selectProposal(preferred.proposal_id);
  } catch (error) {
    proposals.replaceChildren();
    clearSelection();
    session.textContent = `Review request failed: ${error.message}`;
  }
}

async function connect() {
  const supplied = tokenInput.value;
  if (supplied.trim().length === 0) {
    session.textContent = "Enter a nonempty Review credential.";
    return;
  }
  accessToken = supplied;
  tokenInput.value = "";
  refreshButton.disabled = false;
  disconnectButton.disabled = false;
  connectButton.disabled = true;
  await loadProposals();
}

function disconnect() {
  accessToken = null;
  proposals.replaceChildren(node("li", "empty", "Connect to load the prepared proposal."));
  clearSelection();
  refreshButton.disabled = true;
  disconnectButton.disabled = true;
  connectButton.disabled = false;
  session.textContent = "Not connected.";
}

async function submitDecision(action) {
  if (selectedProposal === null) return;
  const reason = reasonInput.value.trim();
  if (reason.length === 0) {
    decisionResult.textContent = "Enter a nonempty decision reason.";
    return;
  }
  approveButton.disabled = true;
  rejectButton.disabled = true;
  decisionResult.textContent = `Submitting ${action.toLowerCase()} decision…`;
  const proposal = selectedProposal;
  const requestIdentity = `${proposal.id}\u0000${proposal.etag}\u0000${action}\u0000${reason}`;
  if (pendingDecision === null || pendingDecision.identity !== requestIdentity) {
    pendingDecision = {identity: requestIdentity, command: commandId()};
  }
  try {
    const result = await requestJson(
      `/api/v1/proposal-packages/${encodeURIComponent(proposal.id)}/decisions`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": pendingDecision.command,
          "If-Match": proposal.etag,
        },
        body: JSON.stringify({
          action,
          manifest_fingerprint: proposal.manifestFingerprint,
          reason,
        }),
      },
    );
    pendingDecision = null;
    await loadProposals(proposal.id);
    decisionResult.textContent = `${action} ${result.body.result_code}: ${result.body.result_ref}`;
  } catch (error) {
    decisionResult.textContent = `${action} failed: ${error.message}`;
    approveButton.disabled = false;
    rejectButton.disabled = false;
  }
}

connectButton.addEventListener("click", () => void connect());
disconnectButton.addEventListener("click", disconnect);
refreshButton.addEventListener("click", () => void loadProposals(selectedProposal?.id || null));
approveButton.addEventListener("click", () => void submitDecision("APPROVE"));
rejectButton.addEventListener("click", () => void submitDecision("REJECT"));
