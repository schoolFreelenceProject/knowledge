import axios, { AxiosError } from "axios";

import { dispatchSessionExpired, getStoredSession } from "./tokenStore";

export const apiClient = axios.create({
  baseURL: "",
  timeout: 120_000,
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
