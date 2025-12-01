// tma_frontend/src/TarotCarousel.jsx
import React, {
  useEffect,
  useMemo,
  useState,
  useCallback,
} from "react";

const TOTAL_CARDS = 78;

function clampIndex(index) {
  const mod = index % TOTAL_CARDS;
  return mod < 0 ? mod + TOTAL_CARDS : mod;
}

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

// =======================
// VIEWER MODE
// =======================

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

// =======================
// PICKER MODE (рулетка)
// =======================

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

  // все карты пойманы — ритуал скрываем
  if (isDone) {
    return null;
  }

  const [currentIndex, setCurrentIndex] = useState(0);
  const [isSpinning, setIsSpinning] = useState(true);

  // Бесконечная прокрутка: индекс 0–77, потом снова 0
  useEffect(() => {
    if (!isSpinning) return;

    const id = window.setInterval(() => {
      setCurrentIndex((prev) => clampIndex(prev + 1));
    }, 80); // скорость, можно подстроить

    return () => window.clearInterval(id);
  }, [isSpinning]);

  // 5 видимых «слотов»: -2, -1, 0, +1, +2 относительно currentIndex
  const visibleIndices = useMemo(() => {
    const res = [];
    for (let offset = -2; offset <= 2; offset += 1) {
      res.push(clampIndex(currentIndex + offset));
    }
    return res;
  }, [currentIndex]);

  const deckArray =
    Array.isArray(deck) && deck.length > 0 ? deck : null;

  const handlePick = useCallback(() => {
    // 1) Если есть реальная колода — вычисляем выбранную карту
    if (deckArray && deckArray.length > 0) {
      const deckIndex = currentIndex % deckArray.length;
      const selectedCard = deckArray[deckIndex];

      if (typeof onPickCard === "function" && selectedCard) {
        onPickCard(selectedCard);
      }
    }

    // 2) Старый контракт — сигнал «+1 карта выбрана»
    if (typeof onPick === "function") {
      onPick();
    }

    // 3) Останавливаем карусель на текущей карте (можно убрать, если не нужно)
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

      <div className="tarot-carousel-window">
        <div className="tarot-carousel-strip">
          {visibleIndices.map((virtualIndex, slot) => {
            const isMain = slot === 2; // центральный слот

            // Если есть deck — подставляем реальные карты по индексу
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
                  "tarot-card-slot" +
                  (isMain ? " tarot-card-slot-main" : "")
                }
              >
                <div
                  className={
                    "tarot-card tarot-card-back" +
                    (isMain ? " tarot-card-main" : "")
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
                    <div className="tarot-card-back-inner" />
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
