// tma_frontend/src/data/tarotDeck.js

import rawDeck from "../../data/tarot_deck.json";

// Минимальная нормализация под фронт.
// ВАЖНО: image_url оставляем как есть — это уже готовый путь/URL из бэка.
function normalizeCard(raw) {
  let code = raw.code || raw.id;

  if (!code) {
    const name = String(raw.name || "").trim().toLowerCase();
    code = name.replace(/\s+/g, "_") || "unknown_card";
  }

  return {
    code,
    name: raw.name || "",
    type: raw.type || null,
    suit: raw.suit || null,
    description: raw.description || null,
    meaning_upright: raw.meaning_upright || null,
    meaning_reversed: raw.meaning_reversed || null,
    image_url: raw.image_url || null,
  };
}

// Полная колода для фронта — тот же источник, что и у бэка.
export const FULL_TAROT_DECK = Array.isArray(rawDeck)
  ? rawDeck.map(normalizeCard)
  : [];
