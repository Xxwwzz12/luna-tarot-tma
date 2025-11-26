import React, { useState } from "react";

const TOTAL_CARDS = 78;

export default function TarotCarousel({
  selectedCount,
  maxCards,
  onSelectCard,
}) {
  const [index, setIndex] = useState(0);

  const handlePrev = () => {
    setIndex((prev) => (prev - 1 + TOTAL_CARDS) % TOTAL_CARDS);
  };

  const handleNext = () => {
    setIndex((prev) => (prev + 1) % TOTAL_CARDS);
  };

  const handleChoose = () => {
    if (selectedCount >= maxCards) return;
    onSelectCard(index);
  };

  const remaining = Math.max(maxCards - selectedCount, 0);

  return (
    <div className="card tarot-carousel">
      <p className="section-title">Выбор карт</p>
      <p className="muted small">
        Пролистайте колоду и нажмите «Выбрать карту», когда будете готовы.
      </p>

      <div className="tarot-carousel-shell">
        <div className="tarot-stack">
          <div className="tarot-card main">
            <span className="tarot-card-back">🜁</span>
          </div>
        </div>

        <div className="carousel-controls">
          <button
            type="button"
            className="btn-ghost"
            onClick={handlePrev}
          >
            ◀
          </button>
          <span className="muted small">
            Карта #{index + 1} из {TOTAL_CARDS}
          </span>
          <button
            type="button"
            className="btn-ghost"
            onClick={handleNext}
          >
            ▶
          </button>
        </div>

        <button
          type="button"
          className="btn-primary"
          onClick={handleChoose}
          disabled={selectedCount >= maxCards}
        >
          {selectedCount >= maxCards ? "Лимит карт выбран" : "Выбрать карту"}
        </button>

        <p className="muted small center">
          Выбрано {selectedCount} / {maxCards}.{" "}
          {remaining > 0 && `Осталось выбрать: ${remaining}.`}
        </p>
      </div>
    </div>
  );
}
