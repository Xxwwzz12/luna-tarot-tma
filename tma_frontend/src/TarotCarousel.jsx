// tma_frontend/src/components/TarotCarousel.jsx
import React, { useState, useEffect } from "react";
import TarotCardView from "./components/TarotCardView.jsx";

const LABELS_3 = ["Прошлое", "Настоящее", "Будущее"];

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
 * Универсальная карусель:
 *
 * mode="viewer":
 *  - selectedCards = currentSpread.cards
 *  - maxCards = 1 | 3
 *
 * mode="picker":
 *  - selectedCards = уже выбранные карты (pickedCards)
 *  - maxCards = 1 | 3
 *  - onSelectCard вызывается при «остановке» крутилки
 *
 * @param {{
 *  mode?: "viewer" | "picker";
 *  selectedCards?: Card[];
 *  maxCards?: number;
 *  onSelectCard?: (card: Card | undefined, index: number) => void;
 * }} props
 */
export default function TarotCarousel({
  mode = "viewer",
  selectedCards = [],
  maxCards = 1,
  onSelectCard,
}) {
  const cards = selectedCards || [];
  const effectiveMode = mode || "viewer";
  const effectiveMaxCards =
    typeof maxCards === "number" ? maxCards : 1;

  // -------------------- VIEWER MODE --------------------
  const [currentIndex, setCurrentIndex] = useState(0);

  // Держим currentIndex в допустимых пределах при смене количества карт
  useEffect(() => {
    if (effectiveMode !== "viewer") return;
    if (!cards.length) return;
    setCurrentIndex((prev) => {
      if (prev < 0) return 0;
      if (prev >= cards.length) return cards.length - 1;
      return prev;
    });
  }, [effectiveMode, cards.length]);

  const handlePrev = () => {
    if (effectiveMode !== "viewer") return;
    if (cards.length <= 1) return;
    setCurrentIndex(
      (prev) => (prev - 1 + cards.length) % cards.length
    );
  };

  const handleNext = () => {
    if (effectiveMode !== "viewer") return;
    if (cards.length <= 1) return;
    setCurrentIndex(
      (prev) => (prev + 1) % cards.length
    );
  };

  // -------------------- PICKER MODE --------------------
  const [isSpinning, setIsSpinning] = useState(true);

  const handleStopSpin = () => {
    if (effectiveMode !== "picker") return;
    if (!isSpinning) return;

    setIsSpinning(false);

    // Здесь пока не знаем, какая именно карта «выбрана»,
    // поэтому отдаём undefined. Внешний код может использовать
    // сам факт вызова onSelectCard, а не саму карту.
    if (typeof onSelectCard === "function") {
      onSelectCard(undefined, 0);
    }
  };

  // -------------------- RENDER: VIEWER --------------------
  if (effectiveMode === "viewer") {
    if (!cards.length) {
      return null;
    }

    // Финальный режим для одной карты (Карта дня)
    if (effectiveMaxCards === 1 && cards.length === 1) {
      const card = cards[0];

      return (
        <div className="tarot-carousel tarot-carousel-final">
          <div className="tarot-carousel-header">
            <h3 className="tarot-carousel-title">Ваша карта дня</h3>
          </div>

          <div className="tarot-carousel-single-card">
            <TarotCardView
              card={card}
              positionLabel={card.positionLabel || "Карта дня"}
            />
          </div>
        </div>
      );
    }

    // Режим трёх карт (или более) — листаем по currentIndex
    const current = cards[currentIndex];

    return (
      <div className="tarot-carousel tarot-carousel-viewer">
        <div className="tarot-carousel-main">
          <button
            type="button"
            className="tarot-carousel-nav tarot-carousel-nav-prev"
            onClick={handlePrev}
            disabled={cards.length <= 1}
          >
            ‹
          </button>

          <div className="tarot-carousel-card-wrapper">
            {current && (
              <TarotCardView
                card={current}
                positionLabel={
                  current.positionLabel ||
                  (effectiveMaxCards === 3
                    ? LABELS_3[currentIndex] || "Карта дня"
                    : "Карта дня")
                }
              />
            )}
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
            {cards.map((_, idx) => (
              <span
                key={idx}
                className={
                  "tarot-carousel-dot" +
                  (idx === currentIndex
                    ? " tarot-carousel-dot-active"
                    : "")
                }
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  // -------------------- RENDER: PICKER --------------------
  // selectedCards здесь = уже выбранные карты (pickedCards),
  // но сама крутилка показывает только рубашку.
  const pickedCount = cards.length;
  const remaining = Math.max(effectiveMaxCards - pickedCount, 0);

  // Если уже выбрали нужное количество карт — picker можно не показывать
  if (pickedCount >= effectiveMaxCards) {
    return null;
  }

  const mainCardClassName = [
    "tarot-card",
    "main",
    isSpinning ? "spinning" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="tarot-carousel tarot-carousel-picker">
      <div className="tarot-carousel-header">
        <h3 className="tarot-carousel-title">Выбор карт</h3>
        <p className="muted small">
          Нажмите на карту, чтобы остановить вращение и выбрать её.
        </p>
        <p className="muted small">
          Выбрано: {pickedCount} / {effectiveMaxCards}.{" "}
          {remaining > 0 && `Осталось выбрать: ${remaining}.`}
        </p>
      </div>

      <div className="tarot-carousel-main">
        <div
          className="tarot-carousel-card-wrapper"
          onClick={handleStopSpin}
        >
          <div className="tarot-stack">
            {/* Левая «призрачная» рубашка */}
            <div className="tarot-card ghost ghost-left">
              <img
                src="/images/tarot/back.png"
                alt="Рубашка карты"
                className="tarot-card-image"
              />
            </div>

            {/* Основная карта — крутится, пока isSpinning === true */}
            <div className={mainCardClassName}>
              <img
                src="/images/tarot/back.png"
                alt="Рубашка карты"
                className="tarot-card-image"
              />
            </div>

            {/* Правая «призрачная» рубашка */}
            <div className="tarot-card ghost ghost-right">
              <img
                src="/images/tarot/back.png"
                alt="Рубашка карты"
                className="tarot-card-image"
              />
            </div>
          </div>
        </div>

        <button
          type="button"
          className="btn-primary tarot-picker-stop-btn"
          onClick={handleStopSpin}
        >
          {isSpinning ? "Поймать карту" : "Карта выбрана"}
        </button>
      </div>
    </div>
  );
}
