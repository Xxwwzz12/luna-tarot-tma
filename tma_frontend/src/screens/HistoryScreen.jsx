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

function makeSnippet(text, maxLength = 140) {
  if (!text) return "";
  const trimmed = text.trim();
  if (trimmed.length <= maxLength) return trimmed;
  return trimmed.slice(0, maxLength).trimEnd() + "…";
}

export default function HistoryScreen({ spreads = [], onSelectSpread }) {
  const handleClick = (id) => {
    if (onSelectSpread) onSelectSpread(id);
  };

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
      <h2>История раскладов</h2>

      <ul className="history-list">
        {spreads.map((spread) => (
          <li
            key={spread.id}
            className={`card history-item ${
              onSelectSpread ? "history-item-clickable" : ""
            }`}
            onClick={() => handleClick(spread.id)}
          >
            <div className="history-header">
              <span className="history-title">
                #{spread.id} • {spread.spread_type} • {spread.category}
              </span>

              <span className="history-date">
                {formatDate(spread.created_at)}
              </span>
            </div>

            {spread.interpretation && (
              <p className="history-snippet">
                {makeSnippet(spread.interpretation)}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
