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

  let res;
  try {
    res = await fetch(url, options);
  } catch (networkError) {
    console.error(`[TMA] Network error ${method} ${path}:`, networkError);
    return {
      ok: false,
      data: null,
      error: { message: "Network error" },
    };
  }

  // 204 No Content → успех без тела
  if (res.status === 204) {
    return { ok: true, data: null, error: null };
  }

  let json;
  try {
    json = await res.json();
  } catch (e) {
    console.error(`[TMA] Failed to parse JSON for ${method} ${path}:`, e);
    return {
      ok: false,
      data: null,
      error: { message: "Invalid JSON response" },
    };
  }

  // HTTP-ошибка
  if (!res.ok) {
    // Если сервер уже вернул APIResponse { ok, data, error } — просто прокидываем
    if (json && typeof json === "object" && "ok" in json) {
      return json;
    }

    // Иначе — формируем fallback-ответ
    return {
      ok: false,
      data: null,
      error: json?.error || { message: `HTTP ${res.status}` },
    };
  }

  // Успех: либо уже APIResponse с полем ok,
  // либо "голый" JSON, который оборачиваем ОДИН раз
  if (json && typeof json === "object" && "ok" in json && "data" in json) {
    return json;
  }

  return { ok: true, data: json, error: null };
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
  return apiGet("/profile"); // { ok, data, error }
}

// Можно использовать, если захочешь, но сейчас App.jsx дергает apiPost напрямую
export function updateProfile(data) {
  return apiPost("/profile", data); // { ok, data, error }
}

// История раскладов
export function fetchSpreads(page = 1, limit = 10) {
  const search = `?page=${page}&limit=${limit}`;
  return apiGet("/spreads" + search); // { ok, data, error }
}

// Создание авто-расклада
export function createAutoSpread(payload) {
  // payload: { mode: "auto", spread_type, category?, question? }
  return apiPost("/spreads", payload); // { ok, data, error }
}

// Вопросы к раскладу
export function fetchSpreadQuestions(spreadId) {
  return apiGet(`/spreads/${spreadId}/questions`); // { ok, data, error }
}

export function askSpreadQuestion(spreadId, payload) {
  // payload: { question: string }
  return apiPost(`/spreads/${spreadId}/questions`, payload); // { ok, data, error }
}
