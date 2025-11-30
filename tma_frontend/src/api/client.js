// tma_frontend/src/api/client.js

// Базовый URL API
const API_BASE_URL =
  (window.__tma && (window.__tma.API_BASE_URL || window.__tma.apiBaseUrl)) ||
  import.meta.env.VITE_API_BASE_URL ||
  "http://localhost:8000";

console.log("[TMA] API_BASE_URL:", API_BASE_URL);

// Сбор заголовков
function buildHeaders(hasBody) {
  const headers = {};

  if (hasBody) {
    headers["Content-Type"] = "application/json";
  }

  const initData =
    (window.__tma && (window.__tma.InitData || window.__tma.initData)) || null;

  if (initData) {
    headers["X-Telegram-Init-Data"] = initData;
  } else {
    headers["X-Dev-User-Id"] = "123";
    headers["X-Dev-Username"] = "dev_user";
  }

  return headers;
}

// Универсальная функция
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
    return { ok: false, data: null, error: { message: "Network error" } };
  }

  if (res.status === 204) {
    return { ok: true, data: null, error: null };
  }

  let json;
  try {
    json = await res.json();
  } catch (e) {
    console.error(`[TMA] JSON parse error ${method} ${path}:`, e);
    return { ok: false, data: null, error: { message: "Invalid JSON response" } };
  }

  // Оборачиваем ответ в единый формат
  if (!res.ok) {
    console.error(`[TMA] API error ${res.status} ${method} ${path}:`, json);
    return { ok: false, data: json?.data || null, error: json?.error || { message: "API error" } };
  }

  return {
    ok: true,
    data: json,
    error: null,
  };
}

// Обёртки
export function apiGet(path) {
  return apiRequest("GET", path);
}

export function apiPost(path, body) {
  return apiRequest("POST", path, body);
}

// ====== Специализированные API-функции ======

// Профиль
export async function fetchProfile() {
  const resp = await apiGet("/profile");
  return resp; // { ok, data, error }
}

export async function updateProfile(payload) {
  const resp = await apiPost("/profile", payload);
  return resp; // { ok, data, error }
}

// История раскладов
export async function fetchSpreads(page = 1, limit = 10) {
  const resp = await apiGet(`/spreads?page=${page}&limit=${limit}`);
  return resp; // { ok, data, error }
}

// Авто-расклад
export async function createAutoSpread(payload) {
  return apiPost("/spreads", payload); // { ok, data, error }
}

// Вопросы к раскладу
export async function fetchSpreadQuestions(spreadId) {
  return apiGet(`/spreads/${spreadId}/questions`); // { ok, data, error }
}

export async function askSpreadQuestion(spreadId, payload) {
  return apiPost(`/spreads/${spreadId}/questions`, payload); // { ok, data, error }
}
