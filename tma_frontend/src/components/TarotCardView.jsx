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
  const name = card?.name || null;

  const imgClassName =
    "tarot-card-image" + (isReversed ? " tarot-card-image-reversed" : "");

  return (
    <div className="tarot-card-view">
      {positionLabel && (
        <div className="tarot-card-position">
          {positionLabel}
        </div>
      )}

      <div
        className="tarot-card-image-wrapper"
        style={{
          position: "relative",
          maxWidth: "200px",
          margin: "0 auto",
          width: "100%",
          aspectRatio: "3 / 5",
        }}
      >
        <img
          src={imageSrc}
          alt={name || "Карта Таро"}
          className={imgClassName}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            display: "block",
          }}
        />
        {isReversed && (
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
