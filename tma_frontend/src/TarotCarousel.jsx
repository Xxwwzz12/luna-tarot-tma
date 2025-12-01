// tma_frontend/src/TarotCarousel.jsx
import React, { useState, useRef, useEffect } from "react";
import TarotCardView from "./components/TarotCardView.jsx";

const LABELS_3 = ["Прошлое", "Настоящее", "Будущее"];
const REPEAT = 5; // сколько раз повторяем колоду в барабане

/**
 * @typedef {Object} Card
 * @property {string} code
 * @property {string} name
 * @property {string|null} [image_url]
 * @property {boolean} [is_reversed]
 * @property {string|number} [id]
 * @property {string} [positionLabel]
 */

/**
 * @param {{
 *   mode?: "viewer" | "picker";
 *   selectedCards?: Card[];
 *   maxCards?: number;
 *   pickedCount?: number;
 *   onPick?: () => void;
 *   deck?: Card[];                      // полная колода (78 карт)
 *   onPickCard?: (card: Card) => void;  // коллбек с реально выбранной картой
 * }} props
 */
export default function TarotCarousel({
  mode = "viewer",
  selectedCards = [],
  maxCards = 1,
  pickedCount = 0,
  onPick,
  deck,
  onPickCard,
}) {
  const cards = selectedCards || [];
  const effectiveMax = maxCards || cards.length || 1;

  // ===================== VIEWER-МОД (без изменений по контракту) =====================
  if (mode === "viewer") {
    if (!cards.length) {
      return (
        <div className="tarot-carousel tarot-carousel-empty">
          <p className="muted">Карты пока не выбраны.</p>
        </div>
      );
    }

    // 1 карта — карта дня
    if (effectiveMax === 1 || cards.length === 1) {
      const card = cards[0];
      const position = card.positionLabel || "Карта дня";

      return (
        <div className="tarot-carousel tarot-carousel-single">
          <TarotCardView card={card} positionLabel={position} />
        </div>
      );
    }

    // 3 (и более) карты — статичная горизонтальная сетка
    return (
      <div className="tarot-carousel tarot-carousel-multi">
        <div className="tarot-carousel-cards-grid">
          {cards.slice(0, effectiveMax).map((card, index) => (
            <TarotCardView
              key={card.code || card.id || index}
              card={card}
              positionLabel={
                card.positionLabel ||
                LABELS_3[index] ||
                `Карта ${index + 1}`
              }
            />
          ))}
        </div>
      </div>
    );
  }

  // ===================== PICKER-МОД (почти бесконечный барабан) =====================

  const total = maxCards || 1;
  const count = pickedCount || 0;
  const isDone = count >= total;

  // все карты пойманы — рулетку не показываем
  if (isDone) {
    return null;
  }

  const [isLocked, setIsLocked] = useState(false); // только для блокировки кнопки от дабл-клика

  const deckArray = Array.isArray(deck) && deck.length > 0 ? deck : null;

  // формируем "почти бесконечный" пояс
  const wheelItems = deckArray
    ? Array.from(
        { length: REPEAT * deckArray.length },
        (_, idx) => deckArray[idx % deckArray.length]
      )
    : Array.from({ length: 40 }).map(() => null);

  const wheelContainerRef = useRef(null);
  const wheelRef = useRef(null);

  // стартовая позиция — где-то в середине ленты, чтобы ощущение было "бесконечным"
  useEffect(() => {
    if (!wheelContainerRef.current || !deckArray) return;
    const container = wheelContainerRef.current;

    // ширина карты + gap — подгони под реальный CSS при необходимости
    const cardWidth = 56 + 8;
    const middleRepeat = Math.floor(REPEAT / 2);
    container.scrollLeft = middleRepeat * deckArray.length * cardWidth;
  }, [deckArray]);

  function handlePick() {
    if (isLocked) return;

    // Если нет реальной deck → работаем по старому контракту: только onPick
    if (!deckArray || !wheelContainerRef.current) {
      setIsLocked(true);
      onPick?.();
      setIsLocked(false);
      return;
    }

    const container = wheelContainerRef.current;
    const scrollLeft = container.scrollLeft;

    // ширина карты + gap — должен совпадать с версткой
    const cardWidth = 56 + 8;
    const approxIndex = Math.round(scrollLeft / cardWidth);

    const totalItems = REPEAT * deckArray.length;
    const normalizedIndex =
      ((approxIndex % totalItems) + totalItems) % totalItems;
    const baseIndex = normalizedIndex % deckArray.length;

    const selectedCard = deckArray[baseIndex];

    setIsLocked(true);

    // отдаём выбранную карту наружу
    if (typeof onPickCard === "function" && selectedCard) {
      onPickCard(selectedCard);
    }

    // старый сигнал "+1 карта поймана"
    onPick?.();

    // разблокируем кнопку (выбор мгновенный, без таймеров)
    setIsLocked(false);
  }

  return (
    <div className="tarot-carousel tarot-carousel-picker">
      <div className="tarot-carousel-picker-header">
        <p className="muted">
          {total === 1
            ? "Сконцентрируйтесь и поймайте свою карту дня."
            : `Поймайте все ${total} карты, а затем сделайте расклад.`}
        </p>
      </div>

      {/* Контейнер барабана для скролла и маски по краям */}
      <div
        className="tarot-carousel-wheel-container"
        ref={wheelContainerRef}
      >
        <div className="tarot-carousel-wheel" ref={wheelRef}>
          {wheelItems.map((card, idx) => (
            <div key={idx} className="tarot-card wheel-card">
              {card && card.image_url ? (
                <img
                  src={card.image_url}
                  alt={card.name || "Карта Таро"}
                  className="tarot-card-image"
                />
              ) : (
                <div className="tarot-card-back" />
              )}
            </div>
          ))}
        </div>
      </div>

      <button
        type="button"
        className="btn btn-primary"
        disabled={isLocked}
        onClick={handlePick}
      >
        {total === 1
          ? "Поймать карту"
          : `Поймать карту ${count + 1} из ${total}`}
      </button>
    </div>
  );
}
