// tma_frontend/src/screens/SpreadsScreen.jsx
import React from "react";
import TarotCarousel from "../TarotCarousel";

const CATEGORY_OPTIONS = [
  { code: "love", label: "Любовь" },
  { code: "career", label: "Карьера" },
  { code: "finance", label: "Финансы" },
  { code: "relationships", label: "Отношения" },
  { code: "future", label: "Будущее" },
  { code: "general", label: "Общее" },
];

const SPREAD_TYPE_LABELS = {
  one: "Карта дня",
  three: "3 карты (прошлое / настоящее / будущее)",
};

function getCategoryLabel(code) {
  if (!code) return "";
  const found = CATEGORY_OPTIONS.find((c) => c.code === code);
  return found ? found.label : code;
}

function SpreadsScreen({
  spreadType,
  onSpreadTypeChange,
  category,
  onCategoryChange,
  question,
  onQuestionChange,
  selectedCards,
  onSelectCard,
  onCreateSpread,
  currentSpread,
}) {
  const maxCards = spreadType === "one" ? 1 : 3;
  const selectedCount = Array.isArray(selectedCards)
    ? selectedCards.length
    : 0;

  const trimmedQuestion = (question || "").trim();
  const isCreateDisabled =
    !spreadType ||
    (spreadType === "three" && !category && !trimmedQuestion);

  const handleCreateSpreadClick = () => {
    if (isCreateDisabled) return;

    const trimmed = (question || "").trim();

    // Формирование payload под /spreads
    const payload = {
      mode: "auto",
      spread_type: spreadType || "one",
      category: null,
      question: null,
    };

    if (payload.spread_type === "one") {
      // Карта дня — фиксированная категория
      payload.category = "daily";
    } else if (payload.spread_type === "three") {
      if (trimmed) {
        // Пользовательский вопрос вместо категории
        payload.question = trimmed;
        payload.category = null;
      } else {
        // Категория из чипов, fallback — general
        payload.category = category || "general";
      }
    }

    onCreateSpread?.(payload);
  };

  const renderCardsSummary = () => {
    const cards = currentSpread?.cards;
    if (!cards || !Array.isArray(cards) || cards.length === 0) {
      return <p className="muted">Карты пока не выбраны.</p>;
    }

    const text = cards
      .map((card, idx) => {
        const name = card?.name || card?.title || `Карта ${idx + 1}`;
        const isReversed = card?.is_reversed || card?.reversed;
        return `${name}${isReversed ? " (перевернутая)" : ""}`;
      })
      .join(" / ");

    return <p>{text}</p>;
  };

  return (
    <div className="page page-spreads">
      {/* Тип расклада */}
      <section className="card card-spread-type">
        <h2>Тип расклада</h2>

        <div className="pill-toggle">
          <button
            type="button"
            className={
              spreadType === "one" ? "pill-option active" : "pill-option"
            }
            onClick={() => onSpreadTypeChange?.("one")}
          >
            <span>🃏</span>
            <span>Карта дня</span>
          </button>

          <button
            type="button"
            className={
              spreadType === "three" ? "pill-option active" : "pill-option"
            }
            onClick={() => onSpreadTypeChange?.("three")}
          >
            <span>🔮</span>
            <span>3 карты (П/Н/Б)</span>
          </button>
        </div>
      </section>

      {/* Тема / вопрос */}
      <section className="card card-topic">
        <h2>Тема / вопрос</h2>

        {spreadType === "one" && (
          <p className="muted">
            Для карты дня тема задаётся автоматически: «Что ждёт меня сегодня?»
          </p>
        )}

        {spreadType === "three" && (
          <>
            <div className="chip-row">
              {CATEGORY_OPTIONS.map((opt) => (
                <button
                  key={opt.code}
                  type="button"
                  className={
                    category === opt.code ? "chip chip-active" : "chip"
                  }
                  onClick={() => onCategoryChange?.(opt.code)}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            <div className="field">
              <label htmlFor="spread-question" className="field-label">
                Ваш вопрос (опционально)
              </label>
              <textarea
                id="spread-question"
                className="textarea"
                rows={3}
                value={question || ""}
                onChange={(e) => onQuestionChange?.(e.target.value)}
                placeholder="Например: «Что ждёт меня в ближайшие полгода?»"
              />
            </div>
          </>
        )}
      </section>

      {/* Выбор карт — режим picker */}
      <section className="card card-cards">
        <h2>Выбор карт</h2>
        <p className="muted">
          Выберите {maxCards === 1 ? "карту" : "несколько карт"} через колоду
          (пока это только визуальный ритуал).
        </p>

        <TarotCarousel
          mode="picker"
          maxCards={maxCards}
          pickedCards={selectedCards}
          onSelectCard={onSelectCard}
        />

        <p className="muted">
          Выбрано: {selectedCount} / {maxCards}
        </p>
      </section>

      {/* Кнопка создания расклада */}
      <section className="card card-actions">
        <button
          type="button"
          className="btn-primary"
          disabled={isCreateDisabled}
          onClick={handleCreateSpreadClick}
        >
          Сделать расклад
        </button>

        <p className="muted small">
          Сейчас карты выбираются автоматически. Визуальный выбор через
          карусель появится позже.
        </p>
      </section>

      {/* Текущий расклад — режим viewer */}
      <section className="card section spread-current">
        <div className="spread-current-header">
          <p className="section-title">Текущий расклад</p>
          {currentSpread?.id && <span className="badge-soft">из истории</span>}
        </div>

        {!currentSpread ? (
          <p className="muted small spread-current-empty">
            Пока расклад не создан.
          </p>
        ) : (
          <>
            <div className="spread-meta">
              <div className="spread-meta-row">
                <span className="muted small">ID</span>
                <span>#{currentSpread.id}</span>
              </div>

              <div className="spread-meta-row">
                <span className="muted small">Тип</span>
                <span>
                  {SPREAD_TYPE_LABELS[currentSpread.spread_type] ||
                    currentSpread.spread_type}
                </span>
              </div>

              <div className="spread-meta-row">
                <span className="muted small">Категория</span>
                <span>
                  {currentSpread.category
                    ? getCategoryLabel(currentSpread.category)
                    : "—"}
                </span>
              </div>

              {currentSpread.question && (
                <div className="spread-meta-row">
                  <span className="muted small">Вопрос</span>
                  <span>{currentSpread.question}</span>
                </div>
              )}
            </div>

            <div className="spread-cards">
              {currentSpread && (
                <TarotCarousel
                  mode="viewer"
                  selectedCards={currentSpread.cards || []}
                  maxCards={
                    currentSpread.spread_type === "one" ? 1 : 3
                  }
                />
              )}
              {renderCardsSummary()}
            </div>

            {currentSpread.interpretation && (
              <div className="spread-interpretation">
                <p className="section-subtitle">Интерпретация</p>
                <p className="interpretation-text">
                  {currentSpread.interpretation}
                </p>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}

export default SpreadsScreen;
