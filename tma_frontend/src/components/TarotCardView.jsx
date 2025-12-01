// tma_frontend/src/components/TarotCardView.jsx

import React from "react";

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
  const imageSrc = getCardImageSrc(card);
  const isReversed = !!card?.is_reversed;

  return (
    <div className="tarot-card-view">
      {positionLabel && (
        <div className="tarot-card-position">
          {positionLabel}
        </div>
      )}

      <div className="tarot-card-view-image-wrapper">
        <img
          src={imageSrc}
          alt={card?.name || "Карта Таро"}
          className={isReversed ? "tarot-card-image-reversed" : ""}
        />
      </div>

      {card?.name && (
        <div className="tarot-card-name">
          {card.name}
        </div>
      )}
    </div>
  );
}
