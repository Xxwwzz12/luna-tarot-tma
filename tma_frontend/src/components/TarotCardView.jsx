// tma_frontend/src/components/TarotCardView.jsx

import React from "react";

function getCardImageSrc(card) {
  const fallback = "/images/tarot/back.png";
  if (!card) return fallback;

  // 1) Прямой URL из объекта карты (если когда-нибудь начнём его отдавать с бэка)
  const direct = card.image_url || card.imageUrl || card.image || null;
  if (direct) {
    // Поддерживаем как "images/..." так и "/images/..."
    return direct.startsWith("/") ? direct : `/${direct}`;
  }

  // 2) Пытаемся построить путь по коду карты
  const rawCode = String(card.code || card.slug || card.id || "").trim();
  if (!rawCode) return fallback;

  const normalized = rawCode.toLowerCase();

  // Младшие арканы: wands_*, cups_*, swords_*, pentacles_*
  const minorPrefixes = ["wands_", "cups_", "swords_", "pentacles_"];
  const isMinor = minorPrefixes.some((prefix) =>
    normalized.startsWith(prefix),
  );

  // По табличке:
  // major → /images/major/{code}.jpg
  // minor → /images/minor/{code}.jpg
  const basePath = isMinor ? "/images/minor" : "/images/major";
  return `${basePath}/${normalized}.jpg`;
}

export default function TarotCardView({ card, positionLabel }) {
  if (!card) return null;

  const imageSrc = getCardImageSrc(card);
  const isReversed = !!card?.is_reversed;

  const imgClassName =
    "tarot-card-image" + (isReversed ? " tarot-card-image-reversed" : "");

  const hasName = !!card?.name;

  return (
    <div className="tarot-card-view">
      {positionLabel && (
        <div className="tarot-card-position muted small">
          {positionLabel}
        </div>
      )}

      <div className="tarot-card-image-wrap">
        <img src={imageSrc} alt={card?.name || "Таро"} className={imgClassName} />
      </div>

      <div className="tarot-card-caption">
        {hasName && (
          <div className="tarot-card-name">
            {card.name}
          </div>
        )}
        {hasName && (
          <div className="tarot-card-orientation muted small">
            {card.name} {isReversed ? "(перевернутая)" : "(прямая)"}
          </div>
        )}
      </div>
    </div>
  );
}
