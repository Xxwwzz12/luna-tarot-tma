// tma_frontend/src/screens/SpreadsScreen.jsx

import { useState } from "react";
import TarotCarousel from "../TarotCarousel.jsx";

function getSpreadTitle(spreadType) {
  if (spreadType === "one") return "Карта дня";
  if (spreadType === "three") return "Прошлое / Настоящее / Будущее";
  return "Расклад";
}

export default function SpreadsScreen({
  currentSpread,
  onCreateSpread,       // (payload) => Promise<void>
  onResetCurrentSpread, // () => void
}) {
  const [spreadType, setSpreadType] = useState("one"); // "one" | "three"
  const [category, setCategory] = useState("general");
  const [customQuestion, setCustomQuestion] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleChangeSpreadType = (nextType) => {
    setSpreadType(nextType);
    setError(null);

    if (nextType === "one") {
      // Для карты дня ничего не спрашиваем
      setCategory("daily");
      setCustomQuestion("");
    } else {
      // Три карты — по умолчанию общая категория
      setCategory("general");
      setCustomQuestion("");
    }
  };

  const handleCategoryChange = (nextCat) => {
    setCategory(nextCat);
    // При выборе категории очищаем свой вопрос — жёсткое разделение
    setCustomQuestion("");
    setError(null);
  };

  const handleCustomQuestionChange = (e) => {
    const value = e.target.value;
    setCustomQuestion(value);
    setError(null);

    if (value.trim()) {
      // Есть свой вопрос → категория уже не используется
      setCategory(null);
    } else if (spreadType === "three" && !value.trim() && !category) {
      setCategory("general");
    }
  };

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
    const trimmedQuestion = customQuestion.trim();

    if (trimmedQuestion) {
      return {
        mode: "auto",
        spread_type: "three",
        category: null,
        question: trimmedQuestion,
      };
    }

    // Без вопроса — нужна категория
    const effectiveCategory = category || "general";

    return {
      mode: "auto",
      spread_type: "three",
      category: effectiveCategory,
      question: null,
    };
  };

  const handleSubmit = async () => {
    if (!onCreateSpread || isSubmitting) return;

    try {
      setIsSubmitting(true);
      setError(null);

      const payload = buildPayload();
      await onCreateSpread(payload);
    } catch (e) {
      console.error("[SpreadsScreen] create spread error", e);
      setError("Не удалось сделать расклад. Попробуйте ещё раз.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleNewSpread = () => {
    onResetCurrentSpread?.();
    setError(null);
    setIsSubmitting(false);

    // Возвращаемся к дефолтным настройкам
    setSpreadType("one");
    setCategory("daily");
    setCustomQuestion("");
  };

  // === РЕЖИМ: ещё нет текущего расклада — форма создания ===
  if (!currentSpread) {
    const isThree = spreadType === "three";

    return (
      <div className="page page-spreads">
        <h2 className="section-title">Расклады Таро</h2>

        <div className="card">
          <div className="field-group">
            <label className="field-label">Тип расклада</label>
            <div className="button-group">
              <button
                type="button"
                className={`btn ${
                  spreadType === "one" ? "btn-primary" : "btn-outline"
                }`}
                onClick={() => handleChangeSpreadType("one")}
                disabled={isSubmitting}
              >
                1 карта (Карта дня)
              </button>
              <button
                type="button"
                className={`btn ${
                  spreadType === "three" ? "btn-primary" : "btn-outline"
                }`}
                onClick={() => handleChangeSpreadType("three")}
                disabled={isSubmitting}
              >
                3 карты (П / Н / Б)
              </button>
            </div>
          </div>

          {isThree && (
            <>
              <div className="field-group">
                <label className="field-label">
                  Категория расклада
                  <span className="field-hint">
                    {" "}
                    (при выборе категории свой вопрос очищается)
                  </span>
                </label>
                <div className="button-group">
                  <button
                    type="button"
                    className={`btn ${
                      category === "general" ? "btn-soft" : "btn-outline"
                    }`}
                    onClick={() => handleCategoryChange("general")}
                    disabled={isSubmitting}
                  >
                    Общее
                  </button>
                  <button
                    type="button"
                    className={`btn ${
                      category === "love" ? "btn-soft" : "btn-outline"
                    }`}
                    onClick={() => handleCategoryChange("love")}
                    disabled={isSubmitting}
                  >
                    Любовь
                  </button>
                  <button
                    type="button"
                    className={`btn ${
                      category === "career" ? "btn-soft" : "btn-outline"
                    }`}
                    onClick={() => handleCategoryChange("career")}
                    disabled={isSubmitting}
                  >
                    Работа
                  </button>
                  {/* можно добавить и другие */}
                </div>
              </div>

              <div className="field-group">
                <label className="field-label">
                  Свой вопрос вместо категории
                  <span className="field-hint">
                    {" "}
                    (если введёте вопрос — категория игнорируется)
                  </span>
                </label>
                <textarea
                  className="textarea"
                  placeholder="Напишите ваш вопрос к раскладу…"
                  rows={3}
                  value={customQuestion}
                  onChange={handleCustomQuestionChange}
                  disabled={isSubmitting}
                />
              </div>
            </>
          )}

          {!isThree && (
            <p className="muted">
              Для «Карты дня» категория и вопрос подставляются автоматически.
            </p>
          )}

          {error && <p className="error-text">{error}</p>}

          <div className="actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSubmit}
              disabled={isSubmitting}
            >
              {isSubmitting
                ? "Ответ в процессе, ожидайте…"
                : "Сделать расклад"}
            </button>
          </div>
        </div>

        {isSubmitting && (
          <div className="overlay overlay-block">
            <div className="overlay-content">
              <p>Ответ в процессе, ожидайте…</p>
            </div>
          </div>
        )}
      </div>
    );
  }

  // === РЕЖИМ: текущий расклад готов — показываем результат ===
  const cards = currentSpread.cards || [];
  const title = getSpreadTitle(currentSpread.spread_type);

  return (
    <div className="page page-spreads">
      <h2 className="section-title">Текущий расклад</h2>

      <div className="card">
        <div className="spread-header">
          <div className="spread-title">{title}</div>
          <div className="spread-meta">
            {currentSpread.category && (
              <span>Категория: {currentSpread.category}</span>
            )}
            {currentSpread.question && (
              <span>Вопрос: {currentSpread.question}</span>
            )}
          </div>
        </div>

        <div className="spread-cards">
          <TarotCarousel
            mode="viewer"
            selectedCards={cards}
            maxCards={currentSpread.spread_type === "one" ? 1 : 3}
          />
        </div>

        <div className="spread-interpretation">
          <h3 className="section-subtitle">Интерпретация</h3>
          <p className={currentSpread.interpretation ? "" : "muted"}>
            {currentSpread.interpretation?.trim() ||
              `Интерпретация расклада (${currentSpread.spread_type}/${currentSpread.category || "general"}).`}
          </p>
        </div>

        <div className="spread-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleNewSpread}
          >
            Сделать новый расклад
          </button>
        </div>
      </div>
    </div>
  );
}
