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
export const FULL_TAROT_DECK = Array.isArray(rawDeck)
  ? rawDeck.map(normalizeCard)
  : [];
