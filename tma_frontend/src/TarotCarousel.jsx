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

  // --- picker state (рулетка) ---
  const [isSpinning, setIsSpinning] = useState(true);
  const [isLocked, setIsLocked] = useState(false);
  const [isFlipped, setIsFlipped] = useState(false);

  // ===================== VIEWER-МОД =====================
  if (mode === "viewer") {
    if (!cards.length) {
      return (
        <div className="tarot-carousel tarot-carousel-empty">
          <p className="muted">Карты пока не выбраны.</p>
        </div>
      );
    }

    // 1 карта → одна большая
    if (effectiveMax === 1 || cards.length === 1) {
      const card = cards[0];
      const position = card.positionLabel || "Карта дня";

      return (
        <div className="tarot-carousel tarot-carousel-single">
          <TarotCardView card={card} positionLabel={position} />
        </div>
      );
    }

    // 3 карты → статичная сетка
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

  // ===================== PICKER-МОД (ЖИВАЯ РУЛЕТКА) =====================

  const total = maxCards || 1;
  const count = pickedCount || 0;
  const isDone = count >= total;

  // все карты уже пойманы — не показываем ритуал
  if (isDone) {
    return null;
  }

  const mainCardClassName =
    "tarot-card main" +
    (isSpinning ? " spinning" : "") +
    (isFlipped ? " flipping" : "");

  function handlePick() {
    if (isLocked) return;
    if (!onPick) return;

    // останавливаем вращение, запускаем flip
    setIsLocked(true);
    setIsSpinning(false);
    setIsFlipped(true);

    setTimeout(() => {
      onPick(); // сообщаем наверх: ещё одна карта поймана

      setIsFlipped(false);

      // если это не последняя карта — снова запускаем вращение
      if ((pickedCount || 0) + 1 < (maxCards || 1)) {
        setIsSpinning(true);
        setIsLocked(false);
      }
      // если последняя — при следующем рендере isDone === true, и рулетка исчезнет
    }, 500);
  }

  return (
    <div className="tarot-carousel tarot-carousel-picker">
      <div className="tarot-carousel-picker-header">
        <p className="muted">
          {total === 1
            ? "Сконцентрируйтесь и поймайте свою карту дня."
            : `Поймайте все ${total} карты, а затем сделайте расклад.`}
        </p>
      </div>

      {/* Визуальное колесо из рубашек.
          Настоящее "вращение" можно задать в CSS:
          .tarot-carousel-wheel.spinning { animation: wheel-spin ... } */}
      <div
        className={
          "tarot-carousel-wheel" + (isSpinning ? " spinning" : "")
        }
      >
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="tarot-card wheel-card">
            <div className="tarot-card-back" />
          </div>
        ))}
      </div>

      {/* Центральная карта — аккуратно по центру, с ограничением размеров */}
      <div className="tarot-card main-wrapper">
        <div
          className={mainCardClassName}
          onClick={handlePick}
          style={{
            maxWidth: "220px",
            aspectRatio: "3 / 5",
            margin: "0 auto",
          }}
        >
          <div className="tarot-card-back" />
        </div>
      </div>

      <button
        type="button"
        className="btn btn-primary"
        disabled={isLocked}
        onClick={handlePick}
      >
        {total === 1
          ? "Поймать карту"
          : `Поймать карту ${count + 1} из ${total}`}
      </button>
    </div>
  );
}
