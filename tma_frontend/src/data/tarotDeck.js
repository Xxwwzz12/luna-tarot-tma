// tma_frontend/src/data/tarotDeck.js

import rawDeck from "./tarot_deck.json";

// Минимальная нормализация под фронт.
export function normalizeCard(raw) {
  const code =
    raw.code ||
    raw.id ||
    (raw.name ? raw.name.toLowerCase().replace(/\s+/g, "_") : "unknown_card");

  return {
    id: raw.id ?? null,
    code,
    name: raw.name || "",
    type: raw.type || null,
    suit: raw.suit || null,
    description: raw.description || "",
    image_url: raw.image_url || null,

    meaning_upright: raw.meaning_upright || {},
    meaning_reversed: raw.meaning_reversed || {},
    keywords: raw.keywords || {},
  };
}

// Преобразуем rawDeck и из списка, и из словаря в массив карт.
function toArrayFromRaw(raw) {
  if (Array.isArray(raw)) {
    return raw;
  }

  if (raw && typeof raw === "object") {
    return Object.keys(raw)
      .sort((a, b) => Number(a) - Number(b)) // "0","1","10" → 0,1,10
      .map((key) => raw[key])
      .filter(Boolean);
  }

  return [];
}

const rawDeckArray = toArrayFromRaw(rawDeck);

// Полная колода — всегда массив нормализованных карт.
export const FULL_TAROT_DECK = rawDeckArray.map(normalizeCard);

// Диагностика в dev-режиме.
if (import.meta?.env?.DEV) {
  console.log("[Deck] rawDeck meta", {
    isArray: Array.isArray(rawDeck),
    type: typeof rawDeck,
    keys:
      rawDeck && typeof rawDeck === "object"
        ? Object.keys(rawDeck).length
        : null,
  });

  console.log("[Deck] FULL_TAROT_DECK length:", FULL_TAROT_DECK.length);
}
