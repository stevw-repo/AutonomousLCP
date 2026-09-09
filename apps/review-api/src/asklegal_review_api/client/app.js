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
const proposalDetail = document.querySelector("#proposal-detail");
const reasonInput = document.querySelector("#decision-reason");
const approveButton = document.querySelector("#approve");
const rejectButton = document.querySelector("#reject");
const decisionResult = document.querySelector("#decision-result");

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

function clearSelection() {
  selectedProposal = null;
  pendingDecision = null;
  proposalDetail.textContent = "Select a proposal to inspect its complete package.";
  reasonInput.value = "";
  reasonInput.disabled = true;
  approveButton.disabled = true;
  rejectButton.disabled = true;
  decisionResult.textContent = "";
}

async function selectProposal(proposalId) {
  clearSelection();
  proposalDetail.textContent = "Loading proposal package…";
  try {
    const result = await requestJson(`/api/v1/proposal-packages/${encodeURIComponent(proposalId)}`);
    if (result.etag === null) throw new Error("The proposal version was not supplied.");
    selectedProposal = {
      id: proposalId,
      etag: result.etag,
      manifestFingerprint: result.body.proposal.manifest_fingerprint,
    };
    proposalDetail.textContent = JSON.stringify(result.body, null, 2);
    reasonInput.disabled = false;
    approveButton.disabled = false;
    rejectButton.disabled = false;
  } catch (error) {
    proposalDetail.textContent = `Unable to load proposal: ${error.message}`;
  }
}

async function loadProposals() {
  if (accessToken === null) return;
  session.textContent = "Loading Review proposals…";
  try {
    const result = await requestJson("/api/v1/proposal-packages");
    proposals.replaceChildren(...result.body.items.map((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${item.title} — ${item.status} — ${item.manifest_fingerprint}`;
      button.addEventListener("click", () => void selectProposal(item.proposal_id));

    const node = document.createElement("li");
      node.append(button);
    return node;
    }));
    session.textContent = result.body.items.length === 0
      ? "Connected. No review-ready proposal is available yet."
      : "Connected.";
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
  proposals.replaceChildren();
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
    await loadProposals();
    await selectProposal(proposal.id);
    decisionResult.textContent = `${action} ${result.body.result_code}: ${result.body.result_ref}`;
  } catch (error) {
    decisionResult.textContent = `${action} failed: ${error.message}`;
    approveButton.disabled = false;
    rejectButton.disabled = false;
  }
}

connectButton.addEventListener("click", () => void connect());
disconnectButton.addEventListener("click", disconnect);
refreshButton.addEventListener("click", () => void loadProposals());
approveButton.addEventListener("click", () => void submitDecision("APPROVE"));
rejectButton.addEventListener("click", () => void submitDecision("REJECT"));
