// tma_frontend/src/TarotCarousel.jsx
import React, { useEffect, useMemo, useState, useCallback } from "react";

export default function TarotCarousel({
  mode = "viewer",
  selectedCards = [],
  maxCards,
  pickedCount,
  onPick,
  deck,
  onPickCard,
}) {
  if (mode === "viewer") {
    return <TarotCarouselViewer cards={selectedCards} />;
  }

  return (
    <TarotCarouselPicker
      maxCards={maxCards}
      pickedCount={pickedCount}
      onPick={onPick}
      deck={deck}
      onPickCard={onPickCard}
    />
  );
}

/* =======================
 * VIEWER MODE
 * ======================= */

function TarotCarouselViewer({ cards }) {
  if (!cards || cards.length === 0) return null;

  return (
    <div className="tarot-carousel tarot-carousel-viewer">
      <div className="tarot-carousel-strip">
        {cards.map((card, idx) => {
          const reversed = !!card.is_reversed;
          const src = card.image_url || "/images/tarot/back.png";

          return (
            <div
              className="tarot-card-slot"
              key={card.code || card.id || idx}
            >
              <div
                className={
                  "tarot-card tarot-card-viewer" +
                  (reversed ? " tarot-card-viewer-reversed" : "")
                }
              >
                <img
                  src={src}
                  alt={card.name || "Карта Таро"}
                  className={
                    "tarot-card-image" +
                    (reversed ? " tarot-card-image-reversed" : "")
                  }
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* =======================
 * PICKER MODE
 * ======================= */

function TarotCarouselPicker({
  maxCards,
  pickedCount,
  onPick,
  deck,
  onPickCard,
}) {
  const total = maxCards || 1;
  const count = pickedCount || 0;
  const isDone = count >= total;

  if (isDone) {
    // Все карты уже пойманы – ритуал не показываем
    return null;
  }

  const [currentIndex, setCurrentIndex] = useState(0);
  const [isSpinning, setIsSpinning] = useState(true);

  const deckArray =
    Array.isArray(deck) && deck.length > 0 ? deck : null;

  // Размер круга — по реальной колоде, иначе fallback на 78
  const cardsCount =
    deckArray && deckArray.length > 0 ? deckArray.length : 78;

  function clampIndex(index) {
    const mod = index % cardsCount;
    return mod < 0 ? mod + cardsCount : mod;
  }

  // Бесконечная прокрутка: идём по кругу 0..cardsCount-1
  useEffect(() => {
    if (!isSpinning) return;

    const id = window.setInterval(() => {
      setCurrentIndex((prev) => clampIndex(prev + 1));
    }, 80); // скорость вращения, можно подстроить

    return () => window.clearInterval(id);
  }, [isSpinning]); // только по isSpinning, как в ТЗ

  // Показываем 5 карт: [-2, -1, 0, +1, +2] от текущей
  const visibleIndices = useMemo(() => {
    const res = [];
    for (let offset = -2; offset <= 2; offset += 1) {
      res.push(clampIndex(currentIndex + offset));
    }
    return res;
  }, [currentIndex, cardsCount]);

  const handlePick = useCallback(() => {
    // 1) если есть реальная колода – выбираем карту
    if (deckArray && deckArray.length > 0) {
      const deckIndex = currentIndex % deckArray.length;
      const selectedCard = deckArray[deckIndex];

      if (typeof onPickCard === "function" && selectedCard) {
        onPickCard(selectedCard);
      }
    }

    // 2) старый контракт – просто сигнал «карта поймана»
    if (typeof onPick === "function") {
      onPick();
    }

    // 3) остановить рулетку на пойманной карте
    setIsSpinning(false);
  }, [currentIndex, deckArray, onPick, onPickCard]);

  return (
    <div className="tarot-carousel tarot-carousel-picker">
      <div className="tarot-carousel-picker-header">
        <p className="muted">
          {total === 1
            ? "Сконцентрируйтесь и поймайте свою карту дня."
            : `Поймайте карты (${count + 1} из ${total})`}
        </p>
      </div>

      {/* Обёртка для горизонтального колеса */}
      <div className="tarot-carousel-wheel-container">
        <div className="tarot-carousel-wheel">
          {visibleIndices.map((virtualIndex, slot) => {
            const isMain = slot === 2;

            let card = null;
            if (deckArray && deckArray.length > 0) {
              const deckIndex = virtualIndex % deckArray.length;
              card = deckArray[deckIndex];
            }

            const hasFace = card && card.image_url;
            const imgSrc = hasFace
              ? card.image_url
              : "/images/tarot/back.png";

            return (
              <div
                key={`${virtualIndex}-${slot}`}
                className={
                  "tarot-card-slot wheel-card" +
                  (isMain ? " tarot-card-slot-main" : "")
                }
              >
                <div
                  className={
                    // Класс "main" остаётся для существующего CSS .tarot-card.main
                    "tarot-card" + (isMain ? " main" : "")
                  }
                  onClick={isMain ? handlePick : undefined}
                >
                  {hasFace ? (
                    <img
                      src={imgSrc}
                      alt={card?.name || "Карта Таро"}
                      className="tarot-card-image"
                    />
                  ) : (
                    <div className="tarot-card-back" />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <button
        type="button"
        className="button button-primary"
        onClick={handlePick}
      >
        Поймать карту
      </button>
    </div>
  );
}
