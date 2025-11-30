// tma_frontend/src/screens/HistoryScreen.jsx

import React from "react";

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
      return "Прошлое / Настоящее / Будущее";
    default:
      return "Таро расклад";
  }
}

export default function HistoryScreen({ spreads = [], onSelectSpread }) {
  if (!spreads.length) {
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
        {spreads.map((spread) => {
          const preview = spread.short_preview?.trim() || "";
          const text =
            preview || "Интерпретация пока отсутствует.";

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
                  "history-snippet" +
                  (preview ? "" : " muted")
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
