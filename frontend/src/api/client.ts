import axios, { AxiosError } from "axios";

import { dispatchSessionExpired, getStoredSession } from "./tokenStore";

const DEFAULT_API_TIMEOUT_MS = 1_800_000;
const configuredApiTimeoutMs = Number(import.meta.env.VITE_API_TIMEOUT_MS);
const apiTimeoutMs =
  Number.isFinite(configuredApiTimeoutMs) && configuredApiTimeoutMs > 0
    ? configuredApiTimeoutMs
    : DEFAULT_API_TIMEOUT_MS;

export const apiClient = axios.create({
  baseURL: "",
  timeout: apiTimeoutMs,
});

apiClient.interceptors.request.use((config) => {
  const { accessToken } = getStoredSession();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }

  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      dispatchSessionExpired();
    }

    return Promise.reject(error);
  },
);

export function getErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string" && detail) {
      return detail;
    }

    if (detail && typeof detail === "object") {
      return JSON.stringify(detail);
    }

    if (error.message) {
      return error.message;
    }
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}
