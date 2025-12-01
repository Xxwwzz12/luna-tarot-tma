// tma_frontend/src/TarotCarousel.jsx
import React from "react";
import TarotCardView from "./components/TarotCardView.jsx";

const LABELS_3 = ["Прошлое", "Настоящее", "Будущее"];

export default function TarotCarousel({
  mode = "viewer",
  selectedCards = [],
  maxCards = 1,
  onSelectCard, // пока не используем, оставлен на будущее
}) {
  const cards = selectedCards || [];
  const effectiveMax = maxCards || cards.length || 1;

  // VIEWER: показываем уже готовый расклад
  if (mode === "viewer") {
    if (!cards.length) {
      return (
        <div className="tarot-carousel tarot-carousel-empty">
          <p className="muted">Карты пока не выбраны.</p>
        </div>
      );
    }

    // Одна карта (Карта дня)
    if (effectiveMax === 1 || cards.length === 1) {
      const card = cards[0];
      const position = card.positionLabel || "Карта дня";

      return (
        <div className="tarot-carousel tarot-carousel-single">
          <TarotCardView card={card} positionLabel={position} />
        </div>
      );
    }

    // Три (и более) карты — показываем сразу первые effectiveMax
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

  // PICKER: временно выключен, чтобы не было "мертвой крутилки"
  // Когда появится реальный выбор карт на фронте (а не только на бэке),
  // сюда вернём логику визуального ритуала.
  return null;
}
