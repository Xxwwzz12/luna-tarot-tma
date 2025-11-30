// tma_frontend/src/TarotCarousel.jsx
import React, { useState, useEffect, useRef } from "react";
import TarotCardView from "./components/TarotCardView.jsx";

const DEFAULT_MAX_CARDS = 3;
const PICKER_DECK_SIZE = 12; // сколько виртуальных "рубашек" крутим
const SPIN_INTERVAL_MS = 120; // базовая скорость вращения
const PICKER_STOP_DELAY_MS = 700; // задержка "замедления" перед остановкой

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
 * Универсальный компонент карусели:
 *
 * mode="viewer" (по умолчанию):
 *  - показывает уже выбранные карты (currentSpread.cards)
 *  - maxCards: 1 или 3
 *  - selectedCards: Card[]
 *  - onSelectCard?: (card, index) — опционально, по клику по карте
 *
 * mode="picker":
 *  - визуальная "колода рубашек", которая крутится
 *  - по тапу — "поймать" карту, остановить и вызвать onSelectCard
 *  - maxCards: 1 или 3
 *  - pickedCards: Card[] — снаружи ведём счёт выбранных карт
 *  - onSelectCard: (card, index) => void
 *
 * @param {{
 *  mode?: "picker" | "viewer";
 *  selectedCards?: Card[];
 *  maxCards?: number;
 *  onSelectCard?: (card: Card, index: number) => void;
 *  pickedCards?: Card[];
 * }} props
 */
export default function TarotCarousel({
  mode = "viewer",
  selectedCards,
  maxCards,
  onSelectCard,
  pickedCards,
}) {
  const effectiveMaxCards =
    typeof maxCards === "number" ? maxCards : DEFAULT_MAX_CARDS;

  // --- Общие данные для viewer-режима ---------------------------------------

  const cards = selectedCards ?? [];

  // Если мы в viewer-режиме и карт нет — ничего не показываем
  const isViewer = mode !== "picker";

  // --- viewer: состояние текущего индекса -----------------------------------

  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    if (!isViewer) return;
    if (cards.length === 0) return;
    setCurrentIndex((prev) => {
      if (prev < 0) return 0;
      if (prev >= cards.length) return cards.length - 1;
      return prev;
    });
  }, [isViewer, cards.length]);

  // --- picker: состояние "колеса" -------------------------------------------

  const [deck] = useState(() =>
    Array.from({ length: PICKER_DECK_SIZE }, (_, i) => {
      // Виртуальные карты — фронту важен только ритуал, card можно не использовать
      /** @type {Card} */
      return {
        id: `virtual-${i}`,
        name: "Скрытая карта",
        arcana: "virtual",
        image_url: null,
      };
    })
  );
  const [spinIndex, setSpinIndex] = useState(0);
  const [isSpinning, setIsSpinning] = useState(false);
  const [isSlowingDown, setIsSlowingDown] = useState(false);

  const spinTimerRef = useRef(null);
  const spinIndexRef = useRef(0);

  const pickerPickedCount = pickedCards?.length ?? 0;

  // Запуск/остановка вращения в picker-режиме
  useEffect(() => {
    if (mode !== "picker") {
      // выходим из picker-режима — гарантированно останавливаемся
      if (spinTimerRef.current) {
        clearInterval(spinTimerRef.current);
        spinTimerRef.current = null;
      }
      setIsSpinning(false);
      setIsSlowingDown(false);
      return;
    }

    // Если уже выбрали достаточно карт — больше не крутим и ничего не рендерим
    if (pickerPickedCount >= effectiveMaxCards) {
      if (spinTimerRef.current) {
        clearInterval(spinTimerRef.current);
        spinTimerRef.current = null;
      }
      setIsSpinning(false);
      setIsSlowingDown(false);
      return;
    }

    // Если уже есть таймер — считаем, что крутимся
    if (spinTimerRef.current) {
      return;
    }

    // Стартуем вращение
    setIsSpinning(true);
    setIsSlowingDown(false);

    const intervalId = setInterval(() => {
      setSpinIndex((prev) => {
        const next = (prev + 1) % deck.length;
        spinIndexRef.current = next;
        return next;
      });
    }, SPIN_INTERVAL_MS);

    spinTimerRef.current = intervalId;

    return () => {
      if (spinTimerRef.current) {
        clearInterval(spinTimerRef.current);
        spinTimerRef.current = null;
      }
      setIsSpinning(false);
      setIsSlowingDown(false);
    };
  }, [mode, pickerPickedCount, effectiveMaxCards, deck.length]);

  // --- Вспомогательные функции ----------------------------------------------

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
    if (!isViewer) return;
    if (cards.length <= 1) return;
    setCurrentIndex(
      (prev) => (prev - 1 + cards.length) % cards.length
    );
  };

  const handleNext = () => {
    if (!isViewer) return;
    if (cards.length <= 1) return;
    setCurrentIndex(
      (prev) => (prev + 1) % cards.length
    );
  };

  const handleViewerCardClick = () => {
    if (!isViewer) return;
    if (typeof onSelectCard !== "function") return;
    const card = cards[currentIndex];
    onSelectCard(card, currentIndex);
  };

  // picker: клик по карте — "поймать" карту
  const handlePickerCardClick = () => {
    if (mode !== "picker") return;
    if (!isSpinning || isSlowingDown) return;
    if (pickerPickedCount >= effectiveMaxCards) return;

    setIsSlowingDown(true);

    // Через небольшую задержку "останавливаемся" и выбираем карту
    setTimeout(() => {
      if (spinTimerRef.current) {
        clearInterval(spinTimerRef.current);
        spinTimerRef.current = null;
      }
      setIsSpinning(false);
      setIsSlowingDown(false);

      const finalIndex = spinIndexRef.current;
      const card = deck[finalIndex];

      if (typeof onSelectCard === "function") {
        onSelectCard(card, finalIndex);
      }
      // После этого внешний код обновит pickedCards,
      // эффект useEffect перезапустит вращение, если нужно.
    }, PICKER_STOP_DELAY_MS);
  };

  // --- viewer-режим (просмотр результатов) -----------------------------------

  if (isViewer) {
    // Если карт нет — ничего не показываем
    if (!cards || cards.length === 0) {
      return null;
    }

    const isOneModeFinal = effectiveMaxCards === 1 && cards.length === 1;

    // Финальный режим "Карта дня"
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

    // Режим просмотра нескольких карт
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
            onClick={handleViewerCardClick}
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

  // --- picker-режим (колесо выбора) -----------------------------------------

  // Если уже набрали максимум карт — сам блок выбора не показываем
  if (pickerPickedCount >= effectiveMaxCards) {
    return null;
  }

  const remaining = Math.max(
    effectiveMaxCards - pickerPickedCount,
    0
  );

  const mainCardClasses = [
    "tarot-card",
    "main",
    isSpinning ? "spinning" : "",
    isSlowingDown ? "slowing" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="tarot-carousel tarot-carousel-picker">
      <div className="tarot-carousel-header">
        <div className="tarot-carousel-title">Выбор карт</div>
        <div className="muted small">
          Нажмите на карту, чтобы остановить и выбрать её.
        </div>
        <div className="muted small">
          Выбрано: {pickerPickedCount} / {effectiveMaxCards}.{" "}
          {remaining > 0 && `Осталось выбрать: ${remaining}.`}
        </div>
      </div>

      <div className="tarot-carousel-main">
        <div
          className="tarot-carousel-card-wrapper"
          onClick={handlePickerCardClick}
        >
          <div className="tarot-stack">
            {/* Левая "призрачная" карта */}
            <div className="tarot-card ghost ghost-left">
              <span className="tarot-card-back">🜁</span>
            </div>

            {/* Основная карта — крутится/останавливается */}
            <div className={mainCardClasses}>
              <span className="tarot-card-back">🜁</span>
            </div>

            {/* Правая "призрачная" карта */}
            <div className="tarot-card ghost ghost-right">
              <span className="tarot-card-back">🜁</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
