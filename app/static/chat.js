const form = document.querySelector("#chat-form");
const input = document.querySelector("#question-input");
const sendButton = document.querySelector("#send-button");
const messages = document.querySelector("#messages");
const authForm = document.querySelector("#auth-form");
const emailInput = document.querySelector("#email-input");
const passwordInput = document.querySelector("#password-input");
const registerButton = document.querySelector("#register-button");
const logoutButton = document.querySelector("#logout-button");
const authStatusText = document.querySelector("#auth-status-text");
const viewButtons = document.querySelectorAll("[data-view-target]");
const viewPanels = document.querySelectorAll(".view-panel");

const TOKEN_STORAGE_KEY = "company-rag-access-token";
const EMAIL_STORAGE_KEY = "company-rag-email";
let accessToken = localStorage.getItem(TOKEN_STORAGE_KEY) || "";
let signedInEmail = localStorage.getItem(EMAIL_STORAGE_KEY) || "";

updateAuthState();

window.companyRagAuth = {
  getAccessToken: () => accessToken,
  getSignedInEmail: () => signedInEmail,
  clearSession,
};

viewButtons.forEach((button) => {
  button.addEventListener("click", () => {
    switchView(button.dataset.viewTarget);
  });
});

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await login();
});

registerButton.addEventListener("click", async () => {
  await register();
});

logoutButton.addEventListener("click", () => {
  clearSession();
  appendError("Signed out.");
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!accessToken) {
    appendError("Please log in first.");
    emailInput.focus();
    return;
  }

  const question = input.value.trim();
  if (!question) {
    appendError("Question cannot be empty.");
    input.focus();
    return;
  }

  appendMessage("user", question);
  input.value = "";
  setLoading(true);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ question }),
    });

    const payload = await readJson(response);
    if (response.status === 401) {
      clearSession();
    }

    if (!response.ok) {
      throw new Error(payload.detail || "Request failed.");
    }

    appendAnswer(payload.answer, payload.sources || []);
  } catch (error) {
    appendError(error.message || "Unable to generate an answer.");
  } finally {
    setLoading(false);
    input.focus();
  }
});

async function register() {
  const credentials = readCredentials();
  if (!credentials) {
    return;
  }

  setAuthLoading(true);

  try {
    const response = await fetch("/api/auth/register", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(credentials),
    });
    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(payload.detail || "Registration failed.");
    }

    await login(credentials);
  } catch (error) {
    appendError(error.message || "Registration failed.");
  } finally {
    setAuthLoading(false);
  }
}

async function login(credentials = readCredentials()) {
  if (!credentials) {
    return;
  }

  setAuthLoading(true);

  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(credentials),
    });
    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(payload.detail || "Login failed.");
    }

    setSession(payload.access_token, credentials.email);
    passwordInput.value = "";
    appendMessage("assistant", "Signed in.");
    input.focus();
  } catch (error) {
    appendError(error.message || "Login failed.");
  } finally {
    setAuthLoading(false);
  }
}

function readCredentials() {
  const email = emailInput.value.trim().toLowerCase();
  const password = passwordInput.value;

  if (!email || !password) {
    appendError("Email and password are required.");
    return null;
  }

  return { email, password };
}

function setSession(token, email) {
  accessToken = token || "";
  signedInEmail = email || "";
  localStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
  localStorage.setItem(EMAIL_STORAGE_KEY, signedInEmail);
  updateAuthState();
}

function clearSession() {
  accessToken = "";
  signedInEmail = "";
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(EMAIL_STORAGE_KEY);
  updateAuthState();
}

function updateAuthState() {
  const isAuthenticated = Boolean(accessToken);
  authStatusText.textContent = isAuthenticated ? signedInEmail : "Signed out";
  authForm.hidden = isAuthenticated;
  logoutButton.hidden = !isAuthenticated;
  input.disabled = !isAuthenticated;
  sendButton.disabled = !isAuthenticated;
  input.placeholder = isAuthenticated ? "Type your question..." : "Log in to ask...";
  window.dispatchEvent(
    new CustomEvent("company-rag-auth-change", {
      detail: {
        accessToken,
        signedInEmail,
        isAuthenticated,
      },
    })
  );
}

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

function appendMessage(role, text) {
  const article = document.createElement("article");
  article.className = `message ${role}-message`;

  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = role === "user" ? "You" : "RAG";

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = text;

  article.append(label, body);
  messages.append(article);
  scrollToLatest();
  return article;
}

function appendAnswer(answer, sources) {
  const article = appendMessage("assistant", answer || "No answer returned.");

  if (!sources.length) {
    return;
  }

  const sourceList = document.createElement("div");
  sourceList.className = "sources";

  sources.forEach((source) => {
    const item = document.createElement("div");
    item.className = "source-item";

    const name = document.createElement("span");
    name.className = "source-name";
    name.textContent = source.filename || "Unknown source";

    const page = document.createElement("span");
    page.textContent =
      source.page_number === null || source.page_number === undefined
        ? "Document"
        : `Page ${source.page_number}`;

    const score = document.createElement("span");
    const scoreValue = Number(source.score);
    score.textContent = Number.isFinite(scoreValue)
      ? `Score ${scoreValue.toFixed(4)}`
      : "Score n/a";

    item.append(name, page, score);
    sourceList.append(item);
  });

  article.append(sourceList);
  scrollToLatest();
}

function appendError(message) {
  const article = appendMessage("assistant", message);
  article.classList.add("error-message");
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function setLoading(isLoading) {
  sendButton.disabled = isLoading || !accessToken;
  sendButton.textContent = isLoading ? "Sending" : "Send";
}

function setAuthLoading(isLoading) {
  const buttons = authForm.querySelectorAll("button");
  buttons.forEach((button) => {
    button.disabled = isLoading;
  });
}

function scrollToLatest() {
  messages.scrollTop = messages.scrollHeight;
}

function switchView(targetId) {
  if (!targetId) {
    return;
  }

  viewButtons.forEach((button) => {
    const isActive = button.dataset.viewTarget === targetId;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });

  viewPanels.forEach((panel) => {
    const isActive = panel.id === targetId;
    panel.hidden = !isActive;
    panel.classList.toggle("is-active", isActive);
  });

  window.dispatchEvent(
    new CustomEvent("company-rag-view-change", {
      detail: {
        view: targetId,
      },
    })
  );
}
