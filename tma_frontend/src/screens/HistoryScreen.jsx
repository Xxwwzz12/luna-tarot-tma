// tma_frontend/src/screens/HistoryScreen.jsx

import React, { useState, useEffect } from "react";
import TarotCarousel from "../TarotCarousel";

function formatDate(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("ru-RU", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getSpreadTitle(spreadType) {
  switch (spreadType) {
    case "one":
      return "Карта дня";
    case "three":
      return "Прошлое / Настоящее / Будущее"; // или "П/Н/Б" в UI, если захочешь
    default:
      return "Таро расклад";
  }
}

export default function HistoryScreen({
  spreads,            // { items: SpreadListItem[], total_items, ... } | null
  selectedSpread,     // SpreadDetail | null
  onSelectSpread,     // (id: number) => void
  onAskQuestion,      // (spreadId: number, question: string) => Promise<void>
  isAskingQuestion,
  onCloseDetail,
}) {
  const [localQuestion, setLocalQuestion] = useState("");

  // Сбрасываем поле вопроса при смене расклада
  useEffect(() => {
    setLocalQuestion("");
  }, [selectedSpread?.id]);

  const items = spreads?.items ?? [];
  const hasItems = items.length > 0;

  // Режим списка
  if (!selectedSpread) {
    if (!hasItems) {
      return (
        <div className="page page-history">
          <div className="card">
            <p className="section-title">История раскладов</p>
            <p className="muted">История пока пуста.</p>
          </div>
        </div>
      );
    }

    return (
      <div className="page page-history">
        <h2 className="section-title">История раскладов</h2>

        <ul className="history-list">
          {items.map((spread) => {
            const preview = spread.short_preview?.trim() || "";
            const text = preview || "Интерпретация пока отсутствует.";

            return (
              <li
                key={spread.id}
                className={`card history-item ${
                  onSelectSpread ? "history-item-clickable" : ""
                }`}
                onClick={() => onSelectSpread?.(spread.id)}
              >
                <div className="history-header">
                  <span className="history-title">
                    {getSpreadTitle(spread.spread_type)}
                  </span>
                  <span className="history-date">
                    {formatDate(spread.created_at)}
                  </span>
                </div>

                <p
                  className={
                    "history-snippet" + (preview ? "" : " muted")
                  }
                >
                  {text}
                </p>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  // Режим детали расклада
  const detail = selectedSpread;
  const interpretationText =
    detail.interpretation?.trim() || "Интерпретация пока отсутствует.";

  const handleSubmitQuestion = () => {
    const trimmed = localQuestion.trim();
    if (!trimmed || !detail) return;
    onAskQuestion?.(detail.id, trimmed);
  };

  return (
    <div className="page page-history page-history-detail">
      <button
        type="button"
        className="btn btn-ghost back-button"
        onClick={onCloseDetail}
      >
        ← Назад к списку
      </button>

      <div className="card history-detail-card">
        <div className="history-detail-header">
          <h2 className="section-title">
            Расклад #{detail.id} • {getSpreadTitle(detail.spread_type)}
          </h2>
          <p className="muted small">
            {formatDate(detail.created_at)} • {detail.category}
          </p>
        </div>

        <div className="history-detail-content">
          <div className="history-detail-carousel">
            <TarotCarousel
              selectedCards={detail.cards}
              maxCards={detail.spread_type === "one" ? 1 : 3}
              mode="viewer"
            />
          </div>

          <div className="history-detail-interpretation">
            <h3 className="section-subtitle">Интерпретация</h3>
            <p className={detail.interpretation ? "" : "muted"}>
              {interpretationText}
            </p>
          </div>

          <div className="history-detail-question">
            <h3 className="section-subtitle">Задать уточняющий вопрос</h3>
            <textarea
              className="textarea"
              placeholder="Сформулируйте дополнительный вопрос по этому раскладу…"
              value={localQuestion}
              onChange={(e) => setLocalQuestion(e.target.value)}
              rows={3}
            />
            <button
              type="button"
              className="btn btn-primary"
              disabled={isAskingQuestion || !localQuestion.trim()}
              onClick={handleSubmitQuestion}
            >
              {isAskingQuestion
                ? "Отправляем вопрос…"
                : "Задать вопрос по раскладу"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
