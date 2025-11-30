// tma_frontend/src/api/client.js

// Базовый URL API
const API_BASE_URL =
  (window.__tma && (window.__tma.API_BASE_URL || window.__tma.apiBaseUrl)) ||
  import.meta.env.VITE_API_BASE_URL ||
  "http://localhost:8000";

console.log("[TMA] API_BASE_URL:", API_BASE_URL);

// Собираем заголовки: initData или dev-хедеры
function buildHeaders(hasBody) {
  const headers = {};

  if (hasBody) {
    headers["Content-Type"] = "application/json";
  }

  // Пытаемся взять initData из window.__tma
  const initData =
    (window.__tma && (window.__tma.InitData || window.__tma.initData)) || null;

  if (initData) {
    headers["X-Telegram-Init-Data"] = initData;
  } else {
    // DEV-режим: подставляем фиктивного пользователя
    headers["X-Dev-User-Id"] = "123";
    headers["X-Dev-Username"] = "dev_user";
  }

  return headers;
}

// Общий хелпер для всех запросов
async function apiRequest(method, path, body) {
  const url = API_BASE_URL + path;

  const hasBody = body !== undefined && body !== null;
  const options = {
    method,
    headers: buildHeaders(hasBody),
  };

  if (hasBody) {
    options.body = JSON.stringify(body);
  }

  console.log(`[TMA] API ${method} ${path}`, body || "");

  const res = await fetch(url, options);

  if (!res.ok) {
    let text = "";
    try {
      text = await res.text();
    } catch (e) {
      // ignore
    }
    console.error(
      `[TMA] API error ${res.status} ${method} ${path}:`,
      text || "<empty>"
    );
    throw new Error(`API ${method} ${path} failed: ${res.status}`);
  }

  if (res.status === 204) {
    return null;
  }

  try {
    return await res.json();
  } catch (e) {
    console.error(
      `[TMA] Failed to parse JSON for ${method} ${path}:`,
      e
    );
    throw e;
  }
}

// Универсальные обёртки
export function apiGet(path) {
  return apiRequest("GET", path);
}

export function apiPost(path, body) {
  return apiRequest("POST", path, body);
}

// ==== Специализированные API-функции ====

// Профиль
export function fetchProfile() {
  return apiGet("/profile");
}

// Можно использовать, если захочешь, но сейчас App.jsx дергает apiPost напрямую
export function updateProfile(data) {
  return apiPost("/profile", data);
}

// История раскладов
export function fetchSpreads(page = 1, limit = 10) {
  const search = `?page=${page}&limit=${limit}`;
  return apiGet("/spreads" + search);
}

// Создание авто-расклада
export function createAutoSpread(payload) {
  // payload: { mode: "auto", spread_type, category?, question? }
  return apiPost("/spreads", payload);
}

// Вопросы к раскладу
export function fetchSpreadQuestions(spreadId) {
  return apiGet(`/spreads/${spreadId}/questions`);
}

export function askSpreadQuestion(spreadId, payload) {
  // payload: { question: string }
  return apiPost(`/spreads/${spreadId}/questions`, payload);
}
