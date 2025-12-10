// tma_frontend/src/components/TarotCardView.jsx

import React from "react";

function getCardImageSrc(card) {
  // DEV ЛОГ — помогает отладить отсутствие image_url или code
  if (import.meta?.env?.DEV) {
    console.log("[CardView] card for preview", {
      code: card?.code,
      id: card?.id,
      name: card?.name,
      image_url: card?.image_url,
    });
  }

  if (!card) return "/images/tarot/back.png";

  // 1) Прямое поле
  const direct = card.image_url || card.imageUrl || card.image || null;
  if (direct) return direct;

  // 2) derive по code → /images/tarot/{code}.jpg
  const rawCode = String(card.code || card.slug || "").trim();
  if (rawCode) {
    const normalized = rawCode.toLowerCase();
    return `/images/tarot/${normalized}.jpg`;
  }

  // 3) ФОЛБЭК — только back.png, чтобы избежать 404
  return "/images/tarot/back.png";
}

export default function TarotCardView({ card, positionLabel }) {
  const imageSrc = getCardImageSrc(card);
  const isReversed = !!card?.is_reversed;
  const name = card?.name || null;

  return (
    <div className="tarot-card-view">
      {positionLabel && (
        <div className="tarot-card-position">{positionLabel}</div>
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
          className={
            "tarot-card-image" + (isReversed ? " tarot-card-image-reversed" : "")
          }
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

      {name && <div className="tarot-card-name">{name}</div>}
    </div>
  );
}
