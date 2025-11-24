// tma_frontend/src/api/client.js

// Базовый URL
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// Универсальные заголовки
function getAuthHeaders() {
  const isDevMode = import.meta.env.VITE_TMA_DEV_MODE === "1";

  if (isDevMode) {
    return {
      "X-Dev-User-Id": "123",
      "X-Dev-Username": "dev_user",
    };
  }

  const initData = window.__tma?.initData;
  if (!initData) return {};

  return {
    "X-Telegram-Init-Data": initData,
  };
}

// Обёртки запросов
async function apiGet(path) {
  const isDevMode = import.meta.env.VITE_TMA_DEV_MODE === "1";

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
  });

  let json;
  try {
    json = await res.json();
  } catch {
    throw new Error("Invalid JSON response");
  }

  if (isDevMode) {
    console.log("API GET", path, "→", json);
  }

  if (!res.ok || !json.ok) {
    console.log("API GET error:", json);
    throw new Error(json.error?.message || "GET request failed");
  }

  return json; // APIResponse
}

async function apiPost(path, body) {
  const isDevMode = import.meta.env.VITE_TMA_DEV_MODE === "1";

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(body),
  });

  const json = await res.json().catch(() => null);

  if (isDevMode) {
    console.log("API POST", path, "BODY:", body, "→", json);
  }

  if (!res.ok || !json?.ok) {
    console.log("API POST error:", json);
    throw new Error(json?.error?.message || "POST request failed");
  }

  return json;
}

// High-level API

export async function fetchProfile() {
  const resp = await apiGet("/profile");
  return resp.data;
}

export async function fetchSpreads(page = 1, limit = 10) {
  const resp = await apiGet(`/spreads?page=${page}&limit=${limit}`);
  return resp.data;
}

// Универсальный auto-расклад
export async function createAutoSpread(payload = {}) {
  const body = {
    spread_type: payload.spread_type || "three",
    category: payload.category || "love",
    mode: payload.mode || "auto",
    question: payload.question ?? null,
  };

  const resp = await apiPost("/spreads", body);
  return resp.data;
}

// Обновление профиля
export async function updateProfile(payload) {
  const resp = await apiPost("/profile", payload);
  return resp.data;
}

// -----------------------------
// ТЗ 16.3 — Вопросы к раскладу
// -----------------------------

// 3.1 Получить список вопросов к раскладу
export async function fetchSpreadQuestions(spreadId) {
  const resp = await apiGet(`/spreads/${spreadId}/questions`);
  return resp.data; // apiGet вернул APIResponse → забираем data
}

// 3.2 Отправить вопрос к раскладу
export async function askSpreadQuestion(spreadId, question) {
  const payload = { question };
  const resp = await apiPost(`/spreads/${spreadId}/questions`, payload);
  return resp.data; // возвращаем SpreadQuestionModel
}
