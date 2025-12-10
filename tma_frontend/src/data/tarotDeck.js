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

// Эвристика: понять, что объект "похож на карту".
function isProbablyCard(obj) {
  if (!obj || typeof obj !== "object") return false;

  const hasNameOrId = "name" in obj || "id" in obj;
  const hasImageOrMeanings =
    "image_url" in obj ||
    "meaning_upright" in obj ||
    "meaning_reversed" in obj;

  return hasNameOrId && hasImageOrMeanings;
}

// Рекурсивно собираем все "листовые" объекты-карты из любого уровня вложенности.
function collectCards(node, acc) {
  if (!node) return acc;

  if (Array.isArray(node)) {
    node.forEach((item) => collectCards(item, acc));
    return acc;
  }

  if (typeof node === "object") {
    if (isProbablyCard(node)) {
      acc.push(node);
      return acc;
    }

    // Иначе считаем, что это группа (major, wands, cups, и т.п.)
    Object.values(node).forEach((value) => collectCards(value, acc));
    return acc;
  }

  return acc;
}

const rawCards = collectCards(rawDeck, []);

// Нормализуем каждую найденную карту.
export const FULL_TAROT_DECK = rawCards.map((raw) => normalizeCard(raw));

// 📎 Диагностика — специально без import.meta.env.DEV, чтобы видеть везде.
console.log(
  "[Deck] rawDeck type:",
  typeof rawDeck,
  "isArray:",
  Array.isArray(rawDeck)
);
if (rawDeck && typeof rawDeck === "object") {
  console.log("[Deck] rawDeck top-level keys:", Object.keys(rawDeck));
}
console.log("[Deck] rawCards collected:", rawCards.length);
console.log(
  "[Deck] FULL_TAROT_DECK length:",
  Array.isArray(FULL_TAROT_DECK) ? FULL_TAROT_DECK.length : "not array"
);
