// tma_frontend/src/TarotCarousel.jsx
import React, { useState, useEffect, useRef } from "react";
import TarotCardView from "./components/TarotCardView.jsx";

const DEFAULT_MAX_CARDS = 3;
const PICKER_DECK_SIZE = 12;
const SPIN_INTERVAL_MS = 120;
const PICKER_STOP_DELAY_MS = 700;

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
 * mode="picker":
 *   - selectedCards = уже выбранные карты (фронтовый стейт pickedCards)
 *   - maxCards = 1 | 3
 *   - onSelectCard(card, index) вызывается при выборе НОВОЙ карты
 *
 * mode="viewer":
 *   - selectedCards = currentSpread.cards
 *   - maxCards = 1 | 3
 *   - показывает результат расклада (1 или 3 карты)
 *
 * @param {{
 *  mode?: "viewer" | "picker";
 *  selectedCards?: Card[];
 *  maxCards?: number;
 *  onSelectCard?: (card: Card, index: number) => void;
 * }} props
 */
export default function TarotCarousel(props) {
  const {
    mode = "viewer",
    selectedCards = [],
    maxCards = DEFAULT_MAX_CARDS,
    onSelectCard,
  } = props;

  // Dev-only: компактный лог
  if (import.meta.env.DEV) {
    console.log("[TMA] TarotCarousel props:", {
      mode,
      selectedCardsLength: selectedCards?.length,
      maxCards,
    });
  }

  const effectiveMode = mode || "viewer";
  const cards = selectedCards || [];
  const effectiveMaxCards =
    typeof maxCards === "number" ? maxCards : DEFAULT_MAX_CARDS;

  // --- VIEWER: текущий индекс карты ----------------------------------------

  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    if (effectiveMode !== "viewer") return;
    if (cards.length === 0) return;
    setCurrentIndex((prev) => {
      if (prev < 0) return 0;
      if (prev >= cards.length) return cards.length - 1;
      return prev;
    });
  }, [effectiveMode, cards.length]);

  const LABELS_3 = ["Прошлое", "Настоящее", "Будущее"];

  function handlePrev() {
    if (effectiveMode !== "viewer") return;
    if (cards.length <= 1) return;
    setCurrentIndex((prev) => (prev - 1 + cards.length) % cards.length);
  }

  function handleNext() {
    if (effectiveMode !== "viewer") return;
    if (cards.length <= 1) return;
    setCurrentIndex((prev) => (prev + 1) % cards.length);
  }

  // --- PICKER: вращающаяся "колода" (рубашки back.png) ---------------------

  const [deck] = useState(() =>
    Array.from({ length: PICKER_DECK_SIZE }, (_, i) => {
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

  // В picker-режиме selectedCards = уже выбранные карты (picked)
  const pickerPickedCount = cards.length;

  useEffect(() => {
    if (effectiveMode !== "picker") {
      if (spinTimerRef.current) {
        clearInterval(spinTimerRef.current);
        spinTimerRef.current = null;
      }
      setIsSpinning(false);
      setIsSlowingDown(false);
      return;
    }

    // Уже выбрали все карты — больше не крутим
    if (pickerPickedCount >= effectiveMaxCards) {
      if (spinTimerRef.current) {
        clearInterval(spinTimerRef.current);
        spinTimerRef.current = null;
      }
      setIsSpinning(false);
      setIsSlowingDown(false);
      return;
    }

    // Уже крутится
    if (spinTimerRef.current) return;

    setIsSpinning(true);
    setIsSlowingDown(false);

    const id = setInterval(() => {
      setSpinIndex((prev) => {
        const next = (prev + 1) % deck.length;
        spinIndexRef.current = next;
        return next;
      });
    }, SPIN_INTERVAL_MS);

    spinTimerRef.current = id;

    return () => {
      if (spinTimerRef.current) {
        clearInterval(spinTimerRef.current);
        spinTimerRef.current = null;
      }
      setIsSpinning(false);
      setIsSlowingDown(false);
    };
  }, [effectiveMode, pickerPickedCount, effectiveMaxCards, deck.length]);

  function handlePickerCardClick() {
    if (effectiveMode !== "picker") return;
    if (!isSpinning || isSlowingDown) return;
    if (pickerPickedCount >= effectiveMaxCards) return;

    setIsSlowingDown(true);

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
    }, PICKER_STOP_DELAY_MS);
  }

  // --- РЕЖИМ VIEWER ---------------------------------------------------------

  if (effectiveMode === "viewer") {
    if (!cards || cards.length === 0) return null;

    // spread_type === "one" (maxCards === 1) — финальный режим одной карты
    if (effectiveMaxCards === 1 && cards.length === 1) {
      const card = cards[0];

      return (
        <div className="tarot-carousel tarot-carousel-final">
          <div className="tarot-carousel-header">
            <h3 className="tarot-carousel-title">Ваша карта дня</h3>
          </div>

          <div className="tarot-carousel-single-card">
            <TarotCardView card={card} positionLabel="Карта дня" />
          </div>
        </div>
      );
    }

    // spread_type === "three" (maxCards === 3) — листаем 3 карты
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
                  effectiveMaxCards === 3
                    ? LABELS_3[currentIndex] || null
                    : null
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

  // --- РЕЖИМ PICKER ---------------------------------------------------------

  if (pickerPickedCount >= effectiveMaxCards) {
    // все карты уже выбраны — блок выбора скрываем
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
        <h3 className="tarot-carousel-title">Выбор карт</h3>
        <p className="muted small">
          Нажмите на карту, чтобы остановить и выбрать её.
        </p>
        <p className="muted small">
          Выбрано: {pickerPickedCount} / {effectiveMaxCards}.{" "}
          {remaining > 0 && `Осталось выбрать: ${remaining}.`}
        </p>
      </div>

      <div className="tarot-carousel-main">
        <div
          className="tarot-carousel-card-wrapper"
          onClick={handlePickerCardClick}
        >
          <div className="tarot-stack">
            {/* Левая "призрачная" рубашка */}
            <div className="tarot-card ghost ghost-left">
              <img
                src="/images/tarot/back.png"
                alt="Рубашка карты"
                className="tarot-card-image"
              />
            </div>

            {/* Основная карта — крутится/останавливается */}
            <div className={mainCardClasses}>
              <img
                src="/images/tarot/back.png"
                alt="Рубашка карты"
                className="tarot-card-image"
              />
            </div>

            {/* Правая "призрачная" рубашка */}
            <div className="tarot-card ghost ghost-right">
              <img
                src="/images/tarot/back.png"
                alt="Рубашка карты"
                className="tarot-card-image"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
