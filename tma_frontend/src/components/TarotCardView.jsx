// tma_frontend/src/components/TarotCardView.jsx

import React from "react";

export default function TarotCardView({ card, positionLabel }) {
  if (!card) return null;

  const isReversed = !!card?.is_reversed;

  // Если image_url отсутствует → fallback-рубашка
  const imageSrc = card.image_url || "/images/tarot/back.svg";

  // Логика классов — строго по контракту
  const imageClassName =
    "tarot-card-image" + (isReversed ? " tarot-card-image-reversed" : "");

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
          alt={card.name || "Таро карта"}
          className={imageClassName}
        />
      </div>

      <div className="tarot-card-caption">
        <div className="tarot-card-name">
          {card.name || "Неизвестная карта"}{" "}
          <span className="tarot-card-orientation">
            ({isReversed ? "перевернутая" : "прямая"})
          </span>
        </div>
      </div>
    </div>
  );
}
