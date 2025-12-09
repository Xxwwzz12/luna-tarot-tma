// tma_frontend/src/TarotCarousel.jsx
import React, {
  useEffect,
  useState,
  useCallback,
  useRef,
} from "react";

const TOTAL_CARDS = 78; // fallback, если deck не передана

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

  const deckArray =
    Array.isArray(deck) && deck.length > 0 ? deck : null;

  // Лента реальных карт (или 78 заглушек, если deck нет)
  const cardsArray =
    deckArray && deckArray.length > 0
      ? deckArray
      : Array.from({ length: TOTAL_CARDS }, () => null);
  const cardsCount = cardsArray.length;

  // Индекс текущей "главной" карты в ленте
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isSpinning, setIsSpinning] = useState(true);

  // Реф и шаг для реального скролла
  const wheelRef = useRef(null);
  const [cardStep, setCardStep] = useState(64); // запасной дефолт

  // После первого рендера измеряем ширину слота (карта + gap)
  useEffect(() => {
    if (!wheelRef.current) return;
    const firstCard = wheelRef.current.querySelector(".wheel-card");
    if (firstCard) {
      // ширина + примерно 8px gap (как в CSS)
      setCardStep(firstCard.offsetWidth + 8);
    }
  }, []);

  // Бесконечная смена индекса — чистый автоспин
  useEffect(() => {
    if (!isSpinning) return;

    const id = window.setInterval(() => {
      setCurrentIndex((prev) => {
        const next = prev + 1;
        // жёсткое зацикливание по длине колоды
        return (next % cardsCount + cardsCount) % cardsCount;
      });
    }, 80);

    return () => window.clearInterval(id);
  }, [isSpinning, cardsCount]);

  // Привязка currentIndex к реальному scrollLeft
  useEffect(() => {
    if (!wheelRef.current) return;

    const targetLeft = currentIndex * cardStep;

    wheelRef.current.scrollTo({
      left: targetLeft,
      behavior: "smooth",
    });
  }, [currentIndex, cardStep]);

  const handlePick = useCallback(() => {
    // 🔍 Временный лог для проверки, вызывается ли вообще handlePick
    console.log("[Carousel] handlePick fired", {
      currentIndex,
      cardsCount,
      hasDeck: !!deckArray,
      deckLength: deckArray ? deckArray.length : null,
    });

    // 1) сразу останавливаем спин
    setIsSpinning(false);

    // 2) безопасный индекс в пределах колоды
    const safeIndex =
      (currentIndex % cardsCount + cardsCount) % cardsCount;

    // 3) карта из deck, если она есть
    if (deckArray && deckArray.length > 0) {
      const selectedCard = deckArray[safeIndex];
      if (selectedCard && typeof onPickCard === "function") {
        onPickCard(selectedCard);
      }
    }

    // 4) старый контракт — сигнал наверх
    if (typeof onPick === "function") {
      onPick();
    }
  }, [currentIndex, cardsCount, deckArray, onPick, onPickCard]);

  return (
    <div className="tarot-carousel tarot-carousel-picker">
      <div className="tarot-carousel-picker-header">
        <p className="muted">
          {total === 1
            ? "Сконцентрируйтесь и поймайте свою карту дня."
            : `Поймайте карты (${count + 1} из ${total})`}
        </p>
      </div>

      {/* Обёртка для горизонтального барабана */}
      <div className="tarot-carousel-wheel-container">
        <div className="tarot-carousel-wheel" ref={wheelRef}>
          {cardsArray.map((card, index) => {
            const isMain = index === currentIndex;

            const hasFace = card && card.image_url;
            const imgSrc = hasFace
              ? card.image_url
              : "/images/tarot/back.png";

            return (
              <div
                key={card?.code || card?.id || index}
                className={
                  "tarot-card-slot wheel-card" +
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
                  {/* Debug-метка, чтобы точно видеть, какая карта считается «главной» */}
                  {isMain && (
                    <span
                      className="debug-dot"
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        fontSize: 10,
                      }}
                    >
                      ●
                    </span>
                  )}

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
