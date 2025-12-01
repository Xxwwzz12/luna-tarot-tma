// tma_frontend/src/components/TarotCardView.jsx

import React from "react";

// Логика derive по image_url / code — сохранена
function getCardImageSrc(card) {
  if (!card) return "/images/tarot/back.png";

  const direct = card.image_url || card.imageUrl || card.image || null;
  if (direct) return direct;

  const rawCode = String(card.code || card.slug || "").trim();
  if (rawCode) {
    const normalized = rawCode.toLowerCase();
    return `/images/tarot/${normalized}.jpg`;
  }

  return "/images/tarot/back.png";
}

export default function TarotCardView({ card, positionLabel }) {
  if (!card) return null;

  const { name, is_reversed } = card;
  const reversed = !!is_reversed;
  const src = getCardImageSrc(card);

  return (
    <div className={`tarot-card-view ${reversed ? "tarot-card-view-reversed" : ""}`}>
      {positionLabel && (
        <div className="tarot-card-position">
          {positionLabel}
        </div>
      )}

      <div className="tarot-card-image-wrapper">
        <img
          src={src}
          alt={name || "Карта Таро"}
          className={`tarot-card-image${reversed ? " tarot-card-image-reversed" : ""}`}
        />

        {reversed && (
          <div
            className="tarot-card-reversed-icon"
            title="Перевернутая карта"
          >
            ⇵
          </div>
        )}
      </div>

      {name && (
        <div className="tarot-card-name">
          {name}
        </div>
      )}
    </div>
  );
}
