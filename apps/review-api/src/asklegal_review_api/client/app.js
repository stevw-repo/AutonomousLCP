// Replaceable minimal Review client. Bearer tokens exist only in this module's memory.
const REVIEW_AUDIENCE = "api://asklegal-review";
let accessToken = null;

function base64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

async function beginPkce() {
  const verifierBytes = crypto.getRandomValues(new Uint8Array(48));
  const verifier = base64url(verifierBytes);
  const challenge = base64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  // A host portal supplies the Entra authorize/token endpoints. No token is persisted here.
  document.querySelector("#session").textContent = `PKCE ready for ${REVIEW_AUDIENCE}; challenge ${challenge.slice(0, 12)}…`;
}

async function loadProposals() {
  if (accessToken === null) return;
  const response = await fetch("/api/v1/proposal-packages", {
    headers: {Authorization: `Bearer ${accessToken}`},
    credentials: "omit",
  });
  if (!response.ok) return;
  const page = await response.json();
  const list = document.querySelector("#proposals");
  list.replaceChildren(...page.items.map((item) => {
    const node = document.createElement("li");
    node.textContent = `${item.title} — ${item.status} — ${item.manifest_fingerprint}`;
    return node;
  }));
}

document.querySelector("#sign-in").addEventListener("click", beginPkce);
void loadProposals();
