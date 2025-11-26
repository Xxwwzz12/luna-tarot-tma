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
  // 👇 ТЗ: maxCards зависит от spreadType
  const maxCards = spreadType === "one" ? 1 : 3;

  const selectedCount = selectedCards?.length || 0;

  // 🔐 Логика блокировки кнопки (оставляем как по ТЗ)
  const isCreateDisabled =
    !spreadType ||
    selectedCount === 0 ||
    (spreadType === "three" &&
      !category &&
      !(question && question.trim().length > 0));

  const handleCreateSpreadClick = () => {
    if (isCreateDisabled) return;
    onCreateSpread?.();
  };

  // ─── Вывод списка карт ──────────────────────────────────────────────
  const renderCardsSummary = () => {
    const cards = currentSpread?.cards;
    if (!cards || !Array.isArray(cards) || cards.length === 0) {
      return <p className="muted">Карты пока не выбраны.</p>;
    }

    const text = cards
      .map((card, idx) => {
        const name = card?.name || card?.title || `Карта ${idx + 1}`;
        const rev = card?.is_reversed || card?.reversed;
        return `${name}${rev ? " (перевернутая)" : ""}`;
      })
      .join(" / ");

    return <p>{text}</p>;
  };

  return (
    <div className="page page-spreads">

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* Тип расклада */}
      {/* ─────────────────────────────────────────────────────────────── */}
      <section className="card card-spread-type">
        <h2>Тип расклада</h2>

        <div className="pill-toggle">
          <button
            className={
              spreadType === "one" ? "pill-option active" : "pill-option"
            }
            onClick={() => onSpreadTypeChange?.("one")}
          >
            <span>🃏</span>
            <span>Карта дня</span>
          </button>

          <button
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

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* Тема / вопрос */}
      {/* ─────────────────────────────────────────────────────────────── */}
      <section className="card card-topic">
        <h2>Тема / вопрос</h2>

        {spreadType === "one" && (
          <p className="muted">
            Для карты дня тема задаётся автоматически: «Что ждёт меня
            сегодня?»
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
              <label className="field-label" htmlFor="spread-question">
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

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* Выбор карт */}
      {/* ─────────────────────────────────────────────────────────────── */}
      <section className="card card-cards">
        <h2>Выбор карт</h2>

        <p className="muted">
          Выберите {maxCards === 1 ? "одну карту" : "несколько карт"} в
          колоде.
        </p>

        {/* СЮДА — обновлённый вызов карусели по ТЗ */}
        <TarotCarousel
          selectedCount={selectedCount}
          maxCards={maxCards}
          onSelectCard={onSelectCard}
        />

        <p className="muted">
          Выбрано: {selectedCount} / {maxCards}
        </p>
      </section>

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* Кнопка создания расклада */}
      {/* ─────────────────────────────────────────────────────────────── */}
      <section className="card card-actions">
        <button
          className="btn-primary"
          disabled={isCreateDisabled}
          onClick={handleCreateSpreadClick}
        >
          Сделать расклад
        </button>

        {/* 🔎 Новая подсказка по ТЗ */}
        <p className="muted small">
          Сначала выберите {maxCards === 1 ? "карту" : "несколько карт"} через
          карусель и при необходимости задайте вопрос.
        </p>
      </section>

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* Текущий расклад (с бейджем «из истории») */}
      {/* ─────────────────────────────────────────────────────────────── */}
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

            <div className="spread-cards">{renderCardsSummary()}</div>

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
