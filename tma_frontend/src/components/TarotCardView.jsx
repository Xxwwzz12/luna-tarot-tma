// tma_frontend/src/components/TarotCardView.jsx

import React from "react";

export default function TarotCardView({ card, positionLabel }) {
  if (!card) return null;

  const isReversed = !!card.is_reversed;
  const fallbackSrc = "/images/tarot/back.png";

  // поддерживаем несколько вариантов имени поля на всякий случай
  const imageSrc =
    card.image_url ||
    card.imageUrl ||
    card.image ||
    fallbackSrc;

  const imageClassName =
    "tarot-card-image" + (isReversed ? " tarot-card-image-reversed" : "");

  const orientationLabel = isReversed ? "перевернутая" : "прямая";

  return (
    <div className="tarot-card-view">
      {positionLabel && (
        <div className="tarot-card-position muted small">
          {positionLabel}
        </div>
      )}

      <div className="tarot-card-image-wrap">
        <img
          src={imageSrc}
          alt={card.name || "Карта Таро"}
          className={imageClassName}
        />
      </div>

      <div className="tarot-card-caption">
        {card.name && (
          <div className="tarot-card-name">
            {card.name}
          </div>
        )}
        <div className="tarot-card-orientation">
          {card.name && `${card.name} (${orientationLabel})`}
        </div>
      </div>
    </div>
  );
}
