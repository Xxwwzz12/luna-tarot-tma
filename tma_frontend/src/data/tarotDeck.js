// tma_frontend/src/data/tarotDeck.js

// Импорт реального JSON из соседнего файла.
// JSON лежит в том же каталоге (src/data/).
import rawDeck from "./tarot_deck.json";

// Минимальная нормализация под фронт.
// Задача — привести карту к полностью предсказуемому формату.
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

    // Значения карты (объекты или {})
    meaning_upright: raw.meaning_upright || {},
    meaning_reversed: raw.meaning_reversed || {},

    // Ключевые слова (объект или {})
    keywords: raw.keywords || {},
  };
}

// Полная колода — источник правды для всех компонентов фронта.
//
// Поддерживаем оба варианта структуры JSON:
// 1) Список карт:   [ { ... }, { ... }, ... ]
// 2) Словарь карт:  { "0": { ... }, "1": { ... }, ... }

let rawCardsArray = [];

if (Array.isArray(rawDeck)) {
  rawCardsArray = rawDeck;
} else if (rawDeck && typeof rawDeck === "object") {
  rawCardsArray = Object.values(rawDeck);
} else {
  rawCardsArray = [];
}

export const FULL_TAROT_DECK = rawCardsArray
  .filter(Boolean)
  .map(normalizeCard);
