// tma_frontend/src/TarotCarousel.jsx
import React, { useEffect, useState, useCallback, useRef } from "react";

const TOTAL_FALLBACK_CARDS = 78; // если deck не передана
const LOOP_MULTIPLIER = 5; // во сколько раз размножаем колоду по кругу

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
      deck={deck}
      maxCards={maxCards}
      pickedCount={pickedCount}
      onPick={onPick}
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
 * PICKER MODE — «рулетка»
 * ======================= */

function TarotCarouselPicker({
  deck,
  maxCards,
  pickedCount,
  onPick,
  onPickCard,
}) {
  const total = maxCards || 1;
  const count = pickedCount || 0;
  const isDone = count >= total;

  // Все карты уже пойманы — ритуал не показываем
  if (isDone) {
    return null;
  }

  // Нормализация deck → массив реальных карт
  let deckArray = [];
  if (Array.isArray(deck)) {
    deckArray = deck;
  } else if (deck && typeof deck === "object") {
    deckArray = Object.values(deck).filter(Boolean);
  }

  const baseCount = deckArray.length || TOTAL_FALLBACK_CARDS;

  // Виртуальное размножение колоды по кругу
  const virtualCount = baseCount * LOOP_MULTIPLIER;
  const virtualCards = Array.from({ length: virtualCount }, (_, i) => {
    const realIndex = i % baseCount;
    const card =
      deckArray && deckArray.length > 0 ? deckArray[realIndex] : null;
    return { realIndex, card };
  });

  // Состояния "положения" и выбранных индексов
  const [currentVirtualIndex, setCurrentVirtualIndex] = useState(
    baseCount * Math.floor(LOOP_MULTIPLIER / 2)
  );
  const [cardStep, setCardStep] = useState(64);
  const [usedRealIndices, setUsedRealIndices] = useState([]);

  const wheelRef = useRef(null);
  const hasLoggedDeckRef = useRef(false);

  // Лог deck один раз
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

  // Измеряем шаг карты (width + gap) по первой wheel-card
  useEffect(() => {
    if (!wheelRef.current) return;
    const first = wheelRef.current.querySelector(".wheel-card");
    if (first) {
      const rect = first.getBoundingClientRect();
      setCardStep(rect.width + 8); // 8px — gap в CSS
    }
  }, [virtualCount]);

  // При маунте/смене колоды — стартуем из середины "кольца"
  useEffect(() => {
    if (!wheelRef.current || !cardStep) return;
    const startIndex = baseCount * Math.floor(LOOP_MULTIPLIER / 2);
    setCurrentVirtualIndex(startIndex);
    wheelRef.current.scrollTo({
      left: startIndex * cardStep,
      // "instant" не обязателен, auto достаточно
      behavior: "auto",
    });
  }, [baseCount, cardStep]);

  // Слушаем скролл — обновляем currentVirtualIndex + делаем "бесконечность"
  const handleScroll = useCallback(() => {
    if (!wheelRef.current || !cardStep) return;

    const left = wheelRef.current.scrollLeft || 0;
    const rawIndex = Math.round(left / cardStep);

    // если ушли слишком влево — переносим ближе к центру
    if (rawIndex < baseCount) {
      const newIndex = rawIndex + baseCount * (LOOP_MULTIPLIER - 2);
      wheelRef.current.scrollTo({
        left: newIndex * cardStep,
        behavior: "auto",
      });
      setCurrentVirtualIndex(newIndex);
      return;
    }

    // если ушли слишком вправо — тоже возвращаем к центру
    if (rawIndex > baseCount * (LOOP_MULTIPLIER - 1)) {
      const newIndex = rawIndex - baseCount * (LOOP_MULTIPLIER - 2);
      wheelRef.current.scrollTo({
        left: newIndex * cardStep,
        behavior: "auto",
      });
      setCurrentVirtualIndex(newIndex);
      return;
    }

    setCurrentVirtualIndex(rawIndex);
  }, [cardStep, baseCount]);

  // Выбор карты по текущему/принудительному индексу
  const handlePick = useCallback(
    (forcedVirtualIndex) => {
      if (!deckArray.length) {
        // нет реальной колоды — чисто ритуальный onPick
        if (typeof onPick === "function") {
          onPick();
        }
        return;
      }

      if (typeof maxCards === "number" && pickedCount >= maxCards) {
        return;
      }

      const virtualIndex =
        typeof forcedVirtualIndex === "number"
          ? forcedVirtualIndex
          : currentVirtualIndex;

      const realIndex = virtualIndex % deckArray.length;

      // если карту уже выбирали — берём первую доступную
      const isUsed = usedRealIndices.includes(realIndex);
      let chosenRealIndex = realIndex;

      if (isUsed) {
        const all = Array.from(
          { length: deckArray.length },
          (_, i) => i
        );
        const available = all.filter(
          (i) => !usedRealIndices.includes(i)
        );
        if (!available.length) {
          // всё уже выбрано — выходим
          return;
        }
        chosenRealIndex = available[0];
      }

      const card = deckArray[chosenRealIndex];

      console.log("[Carousel] handlePick fired", {
        currentIndex: virtualIndex,
        safeIndex: chosenRealIndex,
        cardsCount: deckArray.length,
        hasDeck: !!deckArray,
        deckLength: deckArray.length,
        selectedCode: card?.code,
      });

      if (card && typeof onPickCard === "function") {
        onPickCard(card);
      }

      setUsedRealIndices((prev) => [...prev, chosenRealIndex]);

      if (typeof onPick === "function") {
        onPick();
      }
    },
    [
      currentVirtualIndex,
      deckArray,
      usedRealIndices,
      maxCards,
      pickedCount,
      onPickCard,
      onPick,
    ]
  );

  // Клик по рубашке:
  // 1) центрируем её
  // 2) сразу считаем выбранной (аналог кнопки)
  const handleCardClick = useCallback(
    (virtualIndex) => {
      if (!wheelRef.current || !cardStep) return;

      setCurrentVirtualIndex(virtualIndex);
      wheelRef.current.scrollTo({
        left: virtualIndex * cardStep,
        behavior: "smooth",
      });

      // сразу "поймать" карту по клику
      handlePick(virtualIndex);
    },
    [cardStep, handlePick]
  );

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
          {virtualCards.map(({ realIndex, card }, i) => {
            const isActive = i === currentVirtualIndex;
            const isPicked = usedRealIndices.includes(realIndex);

            return (
              <div
                key={`${i}-${realIndex}-${card?.code || "x"}`}
                className={
                  "wheel-card" +
                  (isActive ? " wheel-card-active" : "") +
                  (isPicked ? " wheel-card-picked" : "")
                }
                onClick={() => handleCardClick(i)}
              >
                {isPicked && card && card.image_url && (
                  <img
                    src={card.image_url}
                    alt={card.name || "Карта Таро"}
                    className="wheel-card-face"
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Кнопка «Поймать карту» — дублирует поведение клика по активной рубашке */}
      <button
        type="button"
        className="button button-primary"
        onClick={() => handlePick()}
      >
        Поймать карту
      </button>
    </div>
  );
}
