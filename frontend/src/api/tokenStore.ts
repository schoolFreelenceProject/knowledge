const TOKEN_STORAGE_KEY = "company-rag-access-token";
const EMAIL_STORAGE_KEY = "company-rag-email";

export type StoredSession = {
  accessToken: string;
  email: string;
};

export function getStoredSession(): StoredSession {
  return {
    accessToken: localStorage.getItem(TOKEN_STORAGE_KEY) || "",
    email: localStorage.getItem(EMAIL_STORAGE_KEY) || "",
  };
}

export function setStoredSession(accessToken: string, email: string): void {
  localStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
  localStorage.setItem(EMAIL_STORAGE_KEY, email);
}

export function clearStoredSession(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(EMAIL_STORAGE_KEY);
}

export function dispatchSessionExpired(): void {
  window.dispatchEvent(new CustomEvent("company-rag-session-expired"));
}
