// tma_frontend/src/screens/SpreadsScreen.jsx

import { useState } from "react";
import TarotCarousel from "../TarotCarousel";

function getSpreadTitle(spreadType) {
  if (spreadType === "one") return "Карта дня";
  if (spreadType === "three") return "Прошлое / Настоящее / Будущее";
  return "Расклад";
}

const THREE_SPREAD_CATEGORIES = [
  { value: "general", label: "Общее" },
  { value: "love", label: "Любовь и отношения" },
  { value: "career", label: "Карьера и работа" },
  { value: "finance", label: "Деньги и финансы" },
  { value: "health", label: "Самочувствие" },
  { value: "self", label: "Самопознание" },
];

export default function SpreadsScreen({
  currentSpread,
  onCreateSpread,       // (payload) => Promise<void>
  onResetCurrentSpread, // () => void
}) {
  const [spreadType, setSpreadType] = useState("one"); // "one" | "three"
  const [category, setCategory] = useState("general");
  const [customQuestion, setCustomQuestion] = useState("");
  const [useCustomQuestion, setUseCustomQuestion] = useState(false);
  const [pickedCount, setPickedCount] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const maxCards = spreadType === "one" ? 1 : 3;

  const handleChangeSpreadType = (nextType) => {
    setSpreadType(nextType);
    setError(null);
    setPickedCount(0);

    if (nextType === "one") {
      // Для карты дня ничего не спрашиваем
      setCategory("daily");
      setCustomQuestion("");
      setUseCustomQuestion(false);
    } else {
      // Три карты — по умолчанию общая категория
      setCategory("general");
      setCustomQuestion("");
      setUseCustomQuestion(false);
    }
  };

  const handleCategoryChange = (nextCat) => {
    if (useCustomQuestion) return; // при своём вопросе категории неактивны
    setCategory(nextCat);
    setCustomQuestion("");
    setError(null);
  };

  const handleCustomQuestionChange = (e) => {
    const value = e.target.value;
    setCustomQuestion(value);
    setError(null);
  };

  const toggleUseCustomQuestion = () => {
    const next = !useCustomQuestion;
    setUseCustomQuestion(next);
    setError(null);

    if (next) {
      // включили свой вопрос → гасим категорию
      setCategory(null);
    } else {
      // выключили вопрос → возвращаем дефолт категорию
      if (!category) setCategory("general");
      setCustomQuestion("");
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

    if (useCustomQuestion) {
      return {
        mode: "auto",
        spread_type: "three",
        category: null,
        question: trimmedQuestion,
      };
    }

    // без собственного вопроса — используем категорию
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

    // Валидация перед отправкой
    if (spreadType === "three") {
      if (useCustomQuestion) {
        if (!customQuestion.trim()) {
          setError(
            "Пожалуйста, сформулируйте ваш вопрос или выключите опцию «Свой вопрос»."
          );
          return;
        }
      } else {
        if (!category) {
          setError("Пожалуйста, выберите категорию расклада.");
          return;
        }
      }
    }

    // Проверка ритуала выбора карт
    if (pickedCount < maxCards) {
      setError("Сначала выберите все карты, а потом сделайте расклад.");
      return;
    }

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
    setUseCustomQuestion(false);
    setPickedCount(0);
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

            <div className="spread-type-toggle">
              <button
                type="button"
                className={
                  "toggle-pill" +
                  (spreadType === "one" ? " toggle-pill-active" : "")
                }
                onClick={() => handleChangeSpreadType("one")}
                disabled={isSubmitting}
              >
                Карта дня
              </button>

              <button
                type="button"
                className={
                  "toggle-pill" +
                  (spreadType === "three" ? " toggle-pill-active" : "")
                }
                onClick={() => handleChangeSpreadType("three")}
                disabled={isSubmitting}
              >
                3 карты
              </button>
            </div>

            {spreadType === "one" && (
              <p className="muted">
                «Карта дня» — короткое послание о том, что ждёт вас сегодня.
              </p>
            )}
            {spreadType === "three" && (
              <p className="muted">
                «Прошлое / Настоящее / Будущее» — три карты, которые показывают
                динамику ситуации.
              </p>
            )}
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
                <div className="spread-categories">
                  {THREE_SPREAD_CATEGORIES.map((cat) => (
                    <button
                      key={cat.value}
                      type="button"
                      className={
                        "spread-category-chip" +
                        (!useCustomQuestion && category === cat.value
                          ? " active"
                          : "") +
                        (useCustomQuestion ? " disabled" : "")
                      }
                      onClick={() => handleCategoryChange(cat.value)}
                      disabled={isSubmitting || useCustomQuestion}
                    >
                      {cat.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="field-group">
                <label className="field-label">Свой вопрос вместо категории</label>
                <button
                  type="button"
                  className={`btn ${
                    useCustomQuestion ? "btn-soft" : "btn-outline"
                  }`}
                  onClick={toggleUseCustomQuestion}
                  disabled={isSubmitting}
                >
                  Задать свой вопрос
                </button>
              </div>

              {useCustomQuestion && (
                <div className="field-group">
                  <label className="field-label">Ваш вопрос к раскладу</label>
                  <textarea
                    className="textarea"
                    placeholder="Напишите ваш вопрос…"
                    rows={3}
                    value={customQuestion}
                    onChange={handleCustomQuestionChange}
                    disabled={isSubmitting}
                  />
                </div>
              )}
            </>
          )}

          {!isThree && (
            <p className="muted">
              Для «Карты дня» категория и вопрос подставляются автоматически.
            </p>
          )}

          {error && <p className="error-text">{error}</p>}
        </div>

        {/* Ритуал выбора карт */}
        <div className="card spread-picker">
          <h3 className="section-subtitle">Ритуал выбора карт</h3>

          <TarotCarousel
            mode="picker"
            pickedCount={pickedCount}
            maxCards={maxCards}
            onPick={() => {
              setPickedCount((prev) => Math.min(prev + 1, maxCards));
              setError(null);
            }}
          />

          <p className="muted">
            {maxCards === 1
              ? "Сконцентрируйтесь и поймайте свою карту дня."
              : "Поймайте все три карты, а затем сделайте расклад."}
            {pickedCount >= maxCards &&
              " Карты выбраны, можно делать расклад."}
          </p>
        </div>

        <div className="card">
          <div className="actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSubmit}
              disabled={isSubmitting || pickedCount < maxCards}
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
