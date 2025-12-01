// tma_frontend/src/screens/HistoryScreen.jsx

import { useEffect, useState } from "react";
import TarotCarousel from "../TarotCarousel.jsx";

function getSpreadTitle(spreadType) {
  if (spreadType === "one") return "Карта дня";
  if (spreadType === "three") return "Прошлое / Настоящее / Будущее";
  return "Расклад";
}

function formatDate(value) {
  if (!value) return "";
  try {
    const d = new Date(value);
    return d.toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

export default function HistoryScreen({
  spreads,          // либо { items: [...], total_items, ... }, либо массив
  selectedSpread,   // SpreadDetail | null
  onSelectSpread,   // (id: number) => void
  onAskQuestion,    // (spreadId: number, question: string) => Promise<void>
  isAskingQuestion,
  onCloseDetail,
}) {
  const [localQuestion, setLocalQuestion] = useState("");

  // Поддержка двух форматов spreads: объект и массив
  const items = Array.isArray(spreads)
    ? spreads
    : spreads?.items || [];

  const hasItems = items.length > 0;
  const detail = selectedSpread || null;

  useEffect(() => {
    setLocalQuestion("");
  }, [detail?.id]);

  const handleSubmitQuestion = () => {
    const trimmed = localQuestion.trim();
    if (!trimmed || !detail) return;
    onAskQuestion?.(detail.id, trimmed);
  };

  // Режим списка
  if (!detail) {
    return (
      <div className="page page-history">
        <h2 className="section-title">История раскладов</h2>

        {!hasItems && (
          <p className="muted">История пока пуста.</p>
        )}

        {hasItems && (
          <ul className="history-list">
            {items.map((spread) => (
              <li
                key={spread.id}
                className={`card history-item ${
                  onSelectSpread ? "history-item-clickable" : ""
                }`}
                onClick={() => onSelectSpread?.(spread.id)}
              >
                <div className="history-item-header">
                  <div className="history-item-title">
                    {getSpreadTitle(spread.spread_type)}
                  </div>
                  <div className="history-item-date">
                    {formatDate(spread.created_at)}
                  </div>
                </div>

                <div className="history-item-body">
                  <p
                    className={
                      spread.short_preview ? "" : "muted"
                    }
                  >
                    {spread.short_preview?.trim() ||
                      "Интерпретация пока отсутствует."}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  // Режим детали расклада
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
          <div className="history-detail-title">
            Расклад #{detail.id} • {getSpreadTitle(detail.spread_type)}
          </div>
          <div className="history-detail-meta">
            {formatDate(detail.created_at)}
            {detail.category && (
              <> • {detail.category}</>
            )}
          </div>
        </div>

        <div className="history-detail-content">
          <div className="history-detail-carousel">
            <TarotCarousel
              mode="viewer"
              selectedCards={detail.cards || []}
              maxCards={detail.spread_type === "one" ? 1 : 3}
            />
          </div>

          <div className="history-detail-interpretation">
            <h3 className="section-subtitle">Интерпретация</h3>
            <p
              className={
                detail.interpretation ? "" : "muted"
              }
            >
              {detail.interpretation?.trim() ||
                "Интерпретация пока отсутствует."}
            </p>
          </div>

          <div className="history-detail-question">
            <h3 className="section-subtitle">
              Уточняющий вопрос по раскладу
            </h3>

            <textarea
              className="textarea"
              placeholder="Сформулируйте дополнительный вопрос по этому раскладу…"
              value={localQuestion}
              onChange={(e) =>
                setLocalQuestion(e.target.value)
              }
              rows={3}
            />

            <button
              type="button"
              className="btn btn-primary"
              disabled={
                isAskingQuestion ||
                !localQuestion.trim()
              }
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
