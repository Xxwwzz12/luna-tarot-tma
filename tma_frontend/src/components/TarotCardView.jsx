// tma_frontend/src/components/TarotCardView.jsx

import React from "react";

function getCardImageSrc(card) {
  if (!card) return "/images/tarot/back.png";

  // 1) Прямой URL, если когда-нибудь придёт с бэка
  const direct =
    card.image_url ||
    card.imageUrl ||
    card.image ||
    null;

  if (direct) return direct;

  // 2) URL по card.code
  const rawCode = String(card.code || card.slug || "").trim();
  if (rawCode) {
    const normalized = rawCode.toLowerCase();
    // ТЗ 3.1 — кладём именно в /images/tarot/${code}.jpg
    return `/images/tarot/${normalized}.jpg`;
  }

  return "/images/tarot/back.png";
}

export default function TarotCardView({ card, positionLabel }) {
  if (!card) return null;

  const imageSrc = getCardImageSrc(card);

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
        <img
          src={imageSrc}
          alt={card?.name || "Таро"}
          className={imgClassName}
        />
      </div>

      <div className="tarot-card-caption">
        {card?.name && (
          <div className="tarot-card-name">{card.name}</div>
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
