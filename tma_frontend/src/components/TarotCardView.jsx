// tma_frontend/src/components/TarotCardView.jsx

import React from "react";

export default function TarotCardView({ card, positionLabel }) {
  if (!card) return null;

  const src =
    card?.image_url ||
    card?.imageUrl ||
    card?.image ||
    "/images/tarot/back.png";

  const isReversed = !!card?.is_reversed;

  const imgClassName =
    "tarot-card-image" + (isReversed ? " tarot-card-image-reversed" : "");

  return (
    <div className="tarot-card-view">
      {positionLabel && (
        <div className="tarot-card-position muted small">
          {positionLabel}
        </div>
      )}

      <div className="tarot-card-image-wrap">
        <img src={src} alt={card?.name || "Таро"} className={imgClassName} />
      </div>

      <div className="tarot-card-caption">
        {card?.name && (
          <div className="tarot-card-name">
            {card.name}
          </div>
        )}
        {card?.name && (
          <div className="tarot-card-orientation muted small">
            {card.name} {isReversed ? "(перевернутая)" : "(прямая)"}
          </div>
        )}
      </div>
    </div>
  );
}
