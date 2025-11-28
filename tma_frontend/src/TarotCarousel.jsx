// tma_frontend/src/TarotCarousel.jsx
import React, { useState, useRef, useEffect } from "react";
import TarotCardView from "./components/TarotCardView";

const TOTAL_CARDS = 78;
const SWIPE_THRESHOLD = 40; // px для старта спина
const MAX_SPIN_STEPS = 18;  // сколько "шагов" прокрутки
const BASE_DELAY = 60;      // стартовая задержка между шагами (меньше = быстрее)
const DELAY_GROWTH = 22;    // насколько каждый шаг замедляется

export default function TarotCarousel({
  selectedCount,
  maxCards,
  onSelectCard,
  selectedCards = [],
}) {
  const [index, setIndex] = useState(0);
  const [dragStartX, setDragStartX] = useState(null);
  const [dragDeltaX, setDragDeltaX] = useState(0);
  const [isSpinning, setIsSpinning] = useState(false);
  const [direction, setDirection] = useState(1);
  const [flipState, setFlipState] = useState("idle"); // idle | flipping

  const spinTimerRef = useRef(null);

  // Очистка таймера при размонтировании
  useEffect(() => {
    return () => {
      if (spinTimerRef.current) clearTimeout(spinTimerRef.current);
    };
  }, []);

  const stepOnce = (dir) => {
    setIndex((prev) => {
      let next = prev + dir;
      if (next < 0) next = TOTAL_CARDS - 1;
      if (next >= TOTAL_CARDS) next = 0;
      return next;
    });
  };

  const startSpin = (dir) => {
    stopSpin(false);
    setDirection(dir);
    setIsSpinning(true);

    const spinStep = (step) => {
      if (step >= MAX_SPIN_STEPS) {
        setIsSpinning(false);
        spinTimerRef.current = null;
        return;
      }

      stepOnce(dir);

      const delay = BASE_DELAY + step * DELAY_GROWTH;
      spinTimerRef.current = setTimeout(
        () => spinStep(step + 1),
        delay
      );
    };

    spinStep(0);
  };

  const stopSpin = (withSelect = false) => {
    if (spinTimerRef.current) {
      clearTimeout(spinTimerRef.current);
      spinTimerRef.current = null;
    }
    setIsSpinning(false);
    if (withSelect) handleChoose();
  };

  const handlePrev = () => {
    if (!isSpinning) stepOnce(-1);
  };

  const handleNext = () => {
    if (!isSpinning) stepOnce(1);
  };

  const handleChoose = () => {
    if (selectedCount >= maxCards) return;

    onSelectCard(index);

    setFlipState("flipping");
    setTimeout(() => setFlipState("idle"), 600);
  };

  const remaining = Math.max(maxCards - selectedCount, 0);

  // 👉 Свайпы ---------------------------------------------------------

  const startDrag = (clientX) => {
    if (isSpinning) return;
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
      const dir = delta < 0 ? 1 : -1;
      startSpin(dir);
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

  const handleMouseUp = () => endDrag();
  const handleMouseLeave = () => endDrag();

  const handleTouchStart = (e) => {
    if (e.touches?.length) startDrag(e.touches[0].clientX);
  };

  const handleTouchMove = (e) => {
    if (e.touches?.length) moveDrag(e.touches[0].clientX);
  };

  const handleTouchEnd = () => endDrag();

  // 👉 Визуальные эффекты -------------------------------------------------

  const isDragging = dragStartX != null;

  const dragStyle = isDragging
    ? {
        transform: `translateX(${dragDeltaX * 0.3}px) rotate(${dragDeltaX * 0.02}deg)`,
        transition: "none",
      }
    : isSpinning
    ? {
        transform: `rotate(${direction > 0 ? 2 : -2}deg)`,
        transition: "transform 0.12s ease-out",
      }
    : {
        transform: "none",
        transition: "transform 0.12s ease-out",
      };

  const mainCardClasses = [
    "tarot-card",
    "main",
    isDragging ? "dragging" : "",
    isSpinning ? "spinning" : "",
    flipState === "flipping" ? "flipping" : "",
  ]
    .filter(Boolean)
    .join(" ");

  // 👉 Финальный режим --------------------------------------------------

  const isOneMode = maxCards === 1;
  const isThreeMode = maxCards === 3;

  const hasOneSelected = isOneMode && selectedCards.length === 1;
  const hasThreeSelected = isThreeMode && selectedCards.length === 3;

  const hasFullSelection = hasOneSelected || hasThreeSelected;

  return (
    <div className="card tarot-carousel">
      <p className="section-title">Выбор карт</p>

      <p className="muted small">
        {hasFullSelection
          ? "Ваши карты:"
          : "Свайпните по карте, чтобы раскрутить колоду. Нажмите на карту, чтобы остановить и выбрать её."}
      </p>

      <div className="tarot-carousel-shell">
        {/* ---- ФИНАЛЬНЫЙ РЕЖИМ ---- */}
        {hasOneSelected && (
          <div className="tarot-result-stack one">
            <TarotCardView
              card={selectedCards[0]}
              positionLabel="Карта дня"
            />
          </div>
        )}

        {hasThreeSelected && (
          <div className="tarot-result-stack three">
            <TarotCardView
              card={selectedCards[0]}
              positionLabel="Прошлое"
            />
            <TarotCardView
              card={selectedCards[1]}
              positionLabel="Настоящее"
            />
            <TarotCardView
              card={selectedCards[2]}
              positionLabel="Будущее"
            />
          </div>
        )}

        {/* ---- Пока выбор не завершён → старое поведение ---- */}
        {!hasFullSelection && (
          <>
            <div className="tarot-stack">
              <div className="tarot-card ghost ghost-left">
                <span className="tarot-card-back">🜁</span>
              </div>

              <div
                className={mainCardClasses}
                style={dragStyle}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseLeave}
                onTouchStart={handleTouchStart}
                onTouchMove={handleTouchMove}
                onTouchEnd={handleTouchEnd}
                onClick={() => {
                  if (isSpinning) stopSpin(true);
                  else handleChoose();
                }}
              >
                <span className="tarot-card-back">
                  {flipState === "flipping" ? "✨" : "🜁"}
                </span>
              </div>

              <div className="tarot-card ghost ghost-right">
                <span className="tarot-card-back">🜁</span>
              </div>
            </div>

            <div className="carousel-controls">
              <button
                type="button"
                className="btn-ghost"
                onClick={handlePrev}
                disabled={isSpinning}
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
                disabled={isSpinning}
              >
                ▶
              </button>
            </div>

            <button
              type="button"
              className="btn-primary"
              onClick={() =>
                isSpinning ? stopSpin(true) : handleChoose()
              }
              disabled={selectedCount >= maxCards}
            >
              {selectedCount >= maxCards
                ? "Лимит карт выбран"
                : isSpinning
                ? "Поймать карту"
                : "Выбрать карту"}
            </button>

            <p className="muted small center">
              Выбрано {selectedCount} / {maxCards}.{" "}
              {remaining > 0 && `Осталось выбрать: ${remaining}.`}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
