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
 * PICKER MODE — «барабан»
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

  // Все карты уже пойманы — ритуал не показываем.
  // ВАЖНО: никаких хуков до этого return.
  if (isDone) {
    return null;
  }

  // 🔧 Нормализация deck:
  // - если массив → берём как есть;
  // - если объект { "0": {...}, "1": {...} } → Object.values(...);
  // - иначе → null.
  let deckArray = null;

  if (Array.isArray(deck)) {
    deckArray = deck.length > 0 ? deck : null;
  } else if (deck && typeof deck === "object") {
    const vals = Object.values(deck).filter(Boolean);
    deckArray = vals.length > 0 ? vals : null;
  }

  // Лента реальных карт (или 78 заглушек, если deck нет)
  const cardsArray =
    deckArray && deckArray.length > 0
      ? deckArray
      : Array.from({ length: TOTAL_CARDS }, () => null);

  const cardsCount = cardsArray.length;

  // ==== ХУКИ (после раннего return isDone) ====

  const [currentIndex, setCurrentIndex] = useState(0);
  const [cardStep, setCardStep] = useState(64); // базовое значение
  const [usedIndices, setUsedIndices] = useState([]);

  const wheelRef = useRef(null);
  const hasLoggedDeckRef = useRef(false);

  // 🔍 Лог deck только один раз после первого прихода пропа
  useEffect(() => {
    if (hasLoggedDeckRef.current) return;
    hasLoggedDeckRef.current = true;

    console.log("[Carousel] deck prop received", {
      rawType: typeof deck,
      isArray: Array.isArray(deck),
      isNull: deck === null,
      hasKeys:
        deck && typeof deck === "object"
          ? Object.keys(deck).length
          : null,
    });
  }, [deck]);

  // Измеряем шаг по ширине wheel-card (width + gap)
  useEffect(() => {
    if (!wheelRef.current) return;
    const first = wheelRef.current.querySelector(".wheel-card");
    if (first) {
      const rect = first.getBoundingClientRect();
      setCardStep(rect.width + 8); // 8px — gap из CSS
    }
  }, [cardsCount]);

  // Обновляем currentIndex по scrollLeft — чистый пользовательский свайп
  const handleScroll = useCallback(() => {
    if (!wheelRef.current || !cardStep) return;

    const left = wheelRef.current.scrollLeft || 0;
    const rawIndex = Math.round(left / cardStep);
    const safeIndex =
      ((rawIndex % cardsCount) + cardsCount) % cardsCount;

    setCurrentIndex(safeIndex);
  }, [cardStep, cardsCount]);

  // Клик по конкретной рубашке — плавно центрируем её
  const handleCardClick = useCallback(
    (index) => {
      setCurrentIndex(index);
      if (wheelRef.current && cardStep) {
        wheelRef.current.scrollTo({
          left: index * cardStep,
          behavior: "smooth",
        });
      }
    },
    [cardStep]
  );

  // Выбор карты: не повторяем уже выбранные индексы
  const handlePick = useCallback(() => {
    if (!cardsCount) return;

    let safeIndex =
      ((currentIndex % cardsCount) + cardsCount) % cardsCount;

    // Если эту карту уже выбирали — берём первую доступную
    if (usedIndices.includes(safeIndex)) {
      const all = Array.from({ length: cardsCount }, (_, i) => i);
      const available = all.filter((i) => !usedIndices.includes(i));
      if (!available.length) {
        // все карты уже выбраны — выходим
        return;
      }
      safeIndex = available[0];
    }

    const selectedCard =
      deckArray && deckArray.length > 0
        ? deckArray[safeIndex]
        : null;

    console.log("[Carousel] handlePick fired", {
      currentIndex,
      safeIndex,
      cardsCount,
      hasDeck: !!deckArray,
      deckLength: deckArray ? deckArray.length : null,
      selectedCode: selectedCard?.code,
    });

    if (selectedCard && typeof onPickCard === "function") {
      onPickCard(selectedCard);
    }

    setUsedIndices((prev) => [...prev, safeIndex]);

    if (typeof onPick === "function") {
      onPick();
    }
  }, [
    currentIndex,
    cardsCount,
    deckArray,
    usedIndices,
    onPickCard,
    onPick,
  ]);

  return (
    <div className="tarot-carousel tarot-carousel-picker">
      <div className="tarot-carousel-picker-header">
        <p className="muted">
          {total === 1
            ? "Сконцентрируйтесь и поймайте свою карту дня."
            : `Поймайте карты (${count + 1} из ${total})`}
        </p>
      </div>

      <div className="tarot-carousel-wheel-container">
        <div
          ref={wheelRef}
          className="tarot-carousel-wheel"
          onScroll={handleScroll}
        >
          {cardsArray.map((card, index) => (
            <div
              key={card?.code || card?.id || index}
              className={
                "wheel-card" +
                (index === currentIndex ? " wheel-card-active" : "")
              }
              onClick={() => handleCardClick(index)}
            />
          ))}
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
