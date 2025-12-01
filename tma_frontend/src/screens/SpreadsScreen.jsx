// tma_frontend/src/screens/SpreadsScreen.jsx
import React, { useState } from "react";
import TarotCarousel from "../TarotCarousel";

const CATEGORY_OPTIONS = [
  { code: "daily", label: "Карта дня" },
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
  profile,
  currentSpread,        // SpreadDetail | null
  onCreateSpread,       // (payload) => Promise<void>
  onResetCurrentSpread, // () => void
}) {
  // Локальные состояния экрана
  const [spreadType, setSpreadType] = useState("one");   // "one" | "three"
  const [category, setCategory] = useState("daily");     // дефолт для one
  const [question, setQuestion] = useState("");          // свой вопрос только для three
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Чисто фронтовый выбор карт (для picker)
  const [pickedCards, setPickedCards] = useState([]);

  const hasCurrentSpread = !!currentSpread;
  const trimmedQuestion = (question || "").trim();

  const maxCards = spreadType === "one" ? 1 : 3;

  // Обработка выбора карты в режиме picker (простая логика по индексу)
  const handleSelectCard = (cardOrIndex) => {
    setPickedCards((prev) => {
      const exists = prev.includes(cardOrIndex);
      if (exists) {
        return prev.filter((v) => v !== cardOrIndex);
      }
      return [...prev, cardOrIndex];
    });
  };

  // Формирование payload под /spreads
  const buildPayload = () => {
    if (spreadType === "one") {
      return {
        mode: "auto",
        spread_type: "one",
        category: "daily",
        question: null,
      };
    }

    // three-карточный расклад
    let payloadCategory = null;
    let payloadQuestion = null;

    if (trimmedQuestion) {
      // приоритет: свой вопрос
      payloadCategory = null;
      payloadQuestion = trimmedQuestion;
    } else {
      // fallback на категорию
      payloadCategory = category || "general";
      payloadQuestion = null;
    }

    return {
      mode: "auto",
      spread_type: "three",
      category: payloadCategory,
      question: payloadQuestion,
    };
  };

  // Обработчик «Сделать расклад»
  const handleSubmit = async () => {
    if (isSubmitting || !onCreateSpread) return;

    // простая валидация перед отправкой
    if (spreadType === "three") {
      if (!category && !trimmedQuestion) {
        return;
      }
    }

    setIsSubmitting(true);
    try {
      const payload = buildPayload();
      await onCreateSpread(payload);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    onResetCurrentSpread && onResetCurrentSpread();
    // Сбрасываем локальный стейт к дефолту
    setSpreadType("one");
    setCategory("daily");
    setQuestion("");
    setPickedCards([]);
  };

  const isCreateDisabled = (() => {
    if (isSubmitting) return true;
    if (spreadType === "one") {
      return false; // карту дня можно генерить всегда
    }
    // three: нужна либо категория, либо вопрос
    return !category && !trimmedQuestion;
  })();

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
      {/* Режим ДО генерации: нет текущего расклада */}
      {!hasCurrentSpread && (
        <>
          <section className="card card-spread-type">
            <h2>Тип расклада</h2>

            <div className="pill-toggle">
              <button
                type="button"
                className={
                  spreadType === "one" ? "pill-option active" : "pill-option"
                }
                onClick={() => !isSubmitting && setSpreadType("one")}
                disabled={isSubmitting}
              >
                <span>🃏</span>
                <span>Карта дня</span>
              </button>

              <button
                type="button"
                className={
                  spreadType === "three" ? "pill-option active" : "pill-option"
                }
                onClick={() => !isSubmitting && setSpreadType("three")}
                disabled={isSubmitting}
              >
                <span>🔮</span>
                <span>3 карты (П/Н/Б)</span>
              </button>
            </div>
          </section>

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
                <p className="muted small">
                  Выберите категорию или сформулируйте свой вопрос — мы
                  используем что-то одно.
                </p>

                <div className="chip-row">
                  {CATEGORY_OPTIONS.filter(
                    (opt) => opt.code !== "daily" // daily только для one
                  ).map((opt) => (
                    <button
                      key={opt.code}
                      type="button"
                      className={
                        category === opt.code ? "chip chip-active" : "chip"
                      }
                      onClick={() =>
                        !isSubmitting && setCategory(opt.code)
                      }
                      disabled={isSubmitting}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>

                <div className="field">
                  <label
                    htmlFor="spread-question"
                    className="field-label"
                  >
                    Свой вопрос (опционально)
                  </label>
                  <textarea
                    id="spread-question"
                    className="textarea"
                    rows={3}
                    value={question}
                    onChange={(e) =>
                      !isSubmitting && setQuestion(e.target.value)
                    }
                    placeholder="Например: «Что ждёт меня в ближайшие полгода в работе?»"
                    disabled={isSubmitting}
                  />
                </div>
              </>
            )}
          </section>

          {/* Карусель-пикер: чисто визуальная магия */}
          <section className="card card-cards">
            <h2>Выбор карт</h2>
            <p className="muted">
              Выберите {maxCards === 1 ? "карту" : "несколько карт"} через
              колоду (пока это только визуальный ритуал).
            </p>

            <TarotCarousel
              mode="picker"
              maxCards={maxCards}
              pickedCards={pickedCards}
              onSelectCard={handleSelectCard}
            />

            <p className="muted small">
              Сейчас карты выбираются автоматически. Позже здесь появится
              полноценный выбор.
            </p>
          </section>

          <section className="card card-actions">
            <button
              type="button"
              className="btn-primary"
              disabled={isCreateDisabled}
              onClick={handleSubmit}
            >
              {isSubmitting ? "Генерируем расклад..." : "Сделать расклад"}
            </button>
          </section>
        </>
      )}

      {/* Режим ПОСЛЕ генерации: есть currentSpread */}
      {hasCurrentSpread && (
        <section className="card section spread-current">
          <div className="spread-current-header">
            <p className="section-title">Ваш расклад</p>
            {currentSpread?.id && (
              <span className="badge-soft">из истории</span>
            )}
          </div>

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
            <TarotCarousel
              mode="viewer"
              selectedCards={currentSpread.cards || []}
              maxCards={
                currentSpread.spread_type === "one" ? 1 : 3
              }
            />
            {renderCardsSummary()}
          </div>

          <div className="spread-interpretation">
            <p className="section-subtitle">Интерпретация</p>
            {currentSpread.interpretation ? (
              <p className="interpretation-text">
                {currentSpread.interpretation}
              </p>
            ) : (
              <p className="muted">
                Интерпретация пока не готова. Обновите экран чуть позже.
              </p>
            )}
          </div>

          <div className="card card-actions">
            <button
              type="button"
              className="btn-secondary"
              onClick={handleReset}
            >
              Сделать новый расклад
            </button>
          </div>
        </section>
      )}

      {/* Оверлей ожидания только на время submit */}
      {isSubmitting && !hasCurrentSpread && (
        <div className="overlay overlay-block">
          <div className="overlay-content">
            <div className="spinner" />
            <p>Ответ в процессе, ожидайте…</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default SpreadsScreen;
