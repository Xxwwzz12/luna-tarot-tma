// tma_frontend/src/data/tarotDeck.js
import rawDeck from "./tarot_deck.json";

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
    meaning_upright: raw.meaning_upright || {},
    meaning_reversed: raw.meaning_reversed || {},
    keywords: raw.keywords || {},
    image_url: raw.image_url || null,
  };
}

export const FULL_TAROT_DECK = Array.isArray(rawDeck)
  ? rawDeck.map(normalizeCard)
  : [];
