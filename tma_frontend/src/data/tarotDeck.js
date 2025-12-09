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

// ---------------------------
//   ЭКСПОРТ ПОЛНОЙ КОЛОДЫ
// ---------------------------

// FULL_TAROT_DECK должен содержать все 78 карт без модификаций.
export const FULL_TAROT_DECK = Array.isArray(rawDeck)
  ? rawDeck.map(normalizeCard)
  : [];

// ---------------------------
//   DEV-ЛОГ ДЛИНЫ КОЛОДЫ
// ---------------------------
if (import.meta?.env?.DEV) {
  // Ожидаем 78
  console.log("[Deck] FULL_TAROT_DECK length:", FULL_TAROT_DECK.length);
}
