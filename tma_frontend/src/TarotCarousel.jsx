// tma_frontend/src/TarotCarousel.jsx
import React, { useState } from "react";
import TarotCardView from "./components/TarotCardView.jsx";

const LABELS_3 = ["Прошлое", "Настоящее", "Будущее"];

/**
 * @typedef {Object} Card
 * @property {string|number} [id]
 * @property {string} [code]
 * @property {string} name
 * @property {string|null} [suit]
 * @property {string} [arcana]
 * @property {string|null} [image_url]
 * @property {boolean} [is_reversed]
 * @property {string} [positionLabel]
 */

/**
 * @param {{
 *   mode?: "viewer" | "picker";
 *   selectedCards?: Card[];
 *   maxCards?: number;
 *   pickedCount?: number;
 *   onPick?: () => void;
 * }} props
 */
export default function TarotCarousel({
  mode = "viewer",
  selectedCards = [],
  maxCards = 1,
  pickedCount = 0,
  onPick,
}) {
  const cards = selectedCards || [];
  const effectiveMax = maxCards || cards.length || 1;

  // ===================== VIEWER-МОД =====================
  if (mode === "viewer") {
    if (!cards.length) {
      return (
        <div className="tarot-carousel tarot-carousel-empty">
          <p className="muted">Карты пока не выбраны.</p>
        </div>
      );
    }

    // ОДНА КАРТА (карта дня)
    if (effectiveMax === 1 || cards.length === 1) {
      const card = cards[0];
      const position = card.positionLabel || "Карта дня";

      return (
        <div className="tarot-carousel tarot-carousel-single">
          <TarotCardView card={card} positionLabel={position} />
        </div>
      );
    }

    // НЕСКОЛЬКО КАРТ (обычно 3) — показываем сразу сеткой
    return (
      <div className="tarot-carousel tarot-carousel-multi">
        <div className="tarot-carousel-cards-grid">
          {cards.slice(0, effectiveMax).map((card, index) => (
            <TarotCardView
              key={card.code || card.id || index}
              card={card}
              positionLabel={
                card.positionLabel ||
                LABELS_3[index] ||
                `Карта ${index + 1}`
              }
            />
          ))}
        </div>
      </div>
    );
  }

  // ===================== PICKER-МОД (РУЛЕТКА) =====================
  // selectedCards тут НЕ используем — это чистый ритуал.
  const total = maxCards || 1;
  const count = pickedCount || 0;

  // Если уже поймали нужное количество карт — ничего не показываем
  if (count >= total) {
    return null;
  }

  const nextIndex = count + 1;

  const [isSpinning, setIsSpinning] = useState(true);
  const [isLocked, setIsLocked] = useState(false);

  const handlePick = () => {
    if (isLocked) return;

    // Ловим карту: стопаем вращение и даём время на flip-анимацию
    setIsLocked(true);
    setIsSpinning(false);

    setTimeout(() => {
      // Сообщаем наверх, что «одна карта поймана»
      if (typeof onPick === "function") {
        onPick();
      }

      // Сбрасываем локальное состояние для следующей карты
      setIsLocked(false);
      setIsSpinning(true);
    }, 300); // 300мс под CSS-анимацию flipping
  };

  return (
    <div className="tarot-carousel tarot-carousel-picker">
      <div className="tarot-carousel-picker-header">
        <div className="muted">
          {total === 1
            ? "Сконцентрируйтесь и поймайте свою карту дня"
            : `Карта ${nextIndex} из ${total}`}
        </div>
      </div>

      <div className="tarot-carousel-picker-main">
        <div className="tarot-card main-wrapper">
          <div
            className={
              "tarot-card main " +
              (isSpinning ? "spinning " : "") +
              (isLocked ? "flipping " : "")
            }
            onClick={handlePick}
          >
            {/* Рубашка — просто прямоугольник или back-картинка */}
            <div className="tarot-card-back">
              {/* Если используешь картинку рубашки: */}
              {/* <img src="/images/tarot/back.png" alt="Рубашка карты" className="tarot-card-image" /> */}
            </div>
          </div>
        </div>

        <button
          type="button"
          className="btn btn-soft tarot-picker-button"
          onClick={handlePick}
          disabled={isLocked}
        >
          Поймать карту
        </button>
      </div>
    </div>
  );
}
