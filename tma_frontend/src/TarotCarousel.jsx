// tma_frontend/src/TarotCarousel.jsx
import React, { useState } from "react";

const TOTAL_CARDS = 78;
const SWIPE_THRESHOLD = 40; // px

export default function TarotCarousel({
  selectedCount,
  maxCards,
  onSelectCard,
}) {
  const [index, setIndex] = useState(0);
  const [dragStartX, setDragStartX] = useState(null);
  const [dragDeltaX, setDragDeltaX] = useState(0);

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

  const startDrag = (clientX) => {
    setDragStartX(clientX);
    setDragDeltaX(0);
  };

  const moveDrag = (clientX) => {
    if (dragStartX == null) return;
    setDragDeltaX(clientX - dragStartX);
  };

  const endDrag = () => {
    if (dragStartX == null) return;

    const delta = dragDeltaX;

    if (Math.abs(delta) > SWIPE_THRESHOLD) {
      if (delta < 0) {
        handleNext();
      } else {
        handlePrev();
      }
    }

    setDragStartX(null);
    setDragDeltaX(0);
  };

  const handleMouseDown = (e) => {
    e.preventDefault();
    startDrag(e.clientX);
  };

  const handleMouseMove = (e) => {
    if (dragStartX == null) return;
    e.preventDefault();
    moveDrag(e.clientX);
  };

  const handleMouseUp = () => {
    endDrag();
  };

  const handleMouseLeave = () => {
    endDrag();
  };

  const handleTouchStart = (e) => {
    if (!e.touches || e.touches.length === 0) return;
    startDrag(e.touches[0].clientX);
  };

  const handleTouchMove = (e) => {
    if (!e.touches || e.touches.length === 0) return;
    moveDrag(e.touches[0].clientX);
  };

  const handleTouchEnd = () => {
    endDrag();
  };

  const isDragging = dragStartX != null;

  const cardStyle = {
    transform: `translateX(${dragDeltaX * 0.3}px) rotate(${dragDeltaX * 0.02}deg)`,
    transition: isDragging ? "none" : "transform 0.18s ease-out",
  };

  return (
    <div className="card tarot-carousel">
      <p className="section-title">Выбор карт</p>
      <p className="muted small">
        Проведите по карте влево или вправо, чтобы пролистать колоду. Нажмите
        «Выбрать карту», когда будете готовы.
      </p>

      <div className="tarot-carousel-shell">
        <div className="tarot-stack">
          {/* Левая «призрачная» карта */}
          <div className="tarot-card ghost ghost-left">
            <span className="tarot-card-back">🜁</span>
          </div>

          {/* Основная карта — на ней жесты */}
          <div
            className={`tarot-card main ${isDragging ? "dragging" : ""}`}
            style={cardStyle}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseLeave}
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
          >
            <span className="tarot-card-back">🜁</span>
          </div>

          {/* Правая «призрачная» карта */}
          <div className="tarot-card ghost ghost-right">
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
