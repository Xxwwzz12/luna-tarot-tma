import React, { useState } from "react";

export default function TarotCarousel({ selectedCount, maxCards, onSelectCard }) {
  const [index, setIndex] = useState(0);
  const total = 78;

  const handlePrev = () => {
    setIndex((prev) => (prev - 1 + total) % total);
  };

  const handleNext = () => {
    setIndex((prev) => (prev + 1) % total);
  };

  const handlePick = () => {
    if (selectedCount < maxCards) {
      onSelectCard(index);
    }
  };

  return (
    <div className="tarot-carousel">
      <div className="card tarot-carousel-shell">
        <p className="section-title">Выбор карт</p>
        <p className="muted small">
          Крутите колоду и нажмите «Выбрать карту», когда почувствуете момент.
        </p>

        <div className="tarot-stack">
          <div className="tarot-card tarot-card-back main" />
          <div className="tarot-card tarot-card-back ghost-left" />
          <div className="tarot-card tarot-card-back ghost-right" />
        </div>

        <p className="muted small center">
          Карта {index + 1} из {total}
        </p>

        <p className="muted small center">
          Выбрано: {selectedCount} / {maxCards}
        </p>

        <div className="carousel-controls">
          <button type="button" onClick={handlePrev}>
            ◀
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={handlePick}
            disabled={selectedCount >= maxCards}
          >
            Выбрать карту
          </button>
          <button type="button" onClick={handleNext}>
            ▶
          </button>
        </div>
      </div>
    </div>
  );
}
