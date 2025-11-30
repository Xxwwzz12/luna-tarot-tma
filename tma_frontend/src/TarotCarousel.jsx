// tma_frontend/src/TarotCarousel.jsx
import React, { useState, useEffect } from "react";
import TarotCardView from "./components/TarotCardView.jsx";

const DEFAULT_MAX_CARDS = 3;

/**
 * @typedef {Object} Card
 * @property {string|number} id
 * @property {string} name
 * @property {string|null} [suit]
 * @property {string} arcana
 * @property {string|null} [image_url]
 * @property {boolean} [is_reversed]
 * @property {string} [positionLabel]
 */

/**
 * Режим сейчас фактически = "result":
 * - показываем уже готовые карты расклада (1 или несколько),
 * - без спинов/свайпов/выбора,
 * - используется в SpreadsScreen для отображения currentSpread.cards.
 *
 * @param {{
 *  selectedCards?: Card[];
 *  maxCards?: number;
 *  onSelectCard?: (card: Card, index: number) => void;
 * }} props
 */
export default function TarotCarousel({
  selectedCards,
  maxCards,
  onSelectCard,
}) {
  const cards = selectedCards ?? [];
  const effectiveMaxCards =
    typeof maxCards === "number" ? maxCards : DEFAULT_MAX_CARDS;

  // Если карт нет — ничего не рендерим
  if (!cards || cards.length === 0) {
    return null;
  }

  const [currentIndex, setCurrentIndex] = useState(0);

  // Держим currentIndex в пределах доступного диапазона
  useEffect(() => {
    if (cards.length === 0) return;
    setCurrentIndex((prev) => {
      if (prev < 0) return 0;
      if (prev >= cards.length) return cards.length - 1;
      return prev;
    });
  }, [cards.length]);

  const isOneModeFinal = effectiveMaxCards === 1 && cards.length === 1;

  const resolvePositionLabel = (index, card) => {
    if (card && card.positionLabel) return card.positionLabel;

    if (effectiveMaxCards === 3) {
      switch (index) {
        case 0:
          return "Прошлое";
        case 1:
          return "Настоящее";
        case 2:
          return "Будущее";
        default:
          return null;
      }
    }

    return null;
  };

  const handlePrev = () => {
    if (cards.length <= 1) return;
    setCurrentIndex(
      (prev) => (prev - 1 + cards.length) % cards.length
    );
  };

  const handleNext = () => {
    if (cards.length <= 1) return;
    setCurrentIndex(
      (prev) => (prev + 1) % cards.length
    );
  };

  const handleCardClick = () => {
    if (typeof onSelectCard !== "function") return;
    const card = cards[currentIndex];
    onSelectCard(card, currentIndex);
  };

  // --- Финальный режим: одна карта (Карта дня) ---
  if (isOneModeFinal) {
    const card = cards[0];
    const label = card.positionLabel ?? "Карта дня";

    return (
      <div className="tarot-carousel tarot-carousel-final">
        <div className="tarot-carousel-header">
          <div className="tarot-carousel-title">Ваша карта дня</div>
        </div>

        <div className="tarot-carousel-single-card">
          <TarotCardView card={card} positionLabel={label} />
        </div>
      </div>
    );
  }

  // --- Режим просмотра нескольких карт ---
  const currentCard = cards[currentIndex];
  const currentLabel = resolvePositionLabel(currentIndex, currentCard);

  return (
    <div className="tarot-carousel">
      <div className="tarot-carousel-main">
        <button
          type="button"
          className="tarot-carousel-nav tarot-carousel-nav-prev"
          onClick={handlePrev}
          disabled={cards.length <= 1}
        >
          ‹
        </button>

        <div
          className="tarot-carousel-card-wrapper"
          onClick={handleCardClick}
        >
          <TarotCardView
            card={currentCard}
            positionLabel={currentLabel}
          />
        </div>

        <button
          type="button"
          className="tarot-carousel-nav tarot-carousel-nav-next"
          onClick={handleNext}
          disabled={cards.length <= 1}
        >
          ›
        </button>
      </div>

      {cards.length > 1 && (
        <div className="tarot-carousel-dots">
          {cards.map((_, index) => (
            <button
              key={index}
              type="button"
              className={
                "tarot-carousel-dot" +
                (index === currentIndex
                  ? " tarot-carousel-dot-active"
                  : "")
              }
              onClick={() => setCurrentIndex(index)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
