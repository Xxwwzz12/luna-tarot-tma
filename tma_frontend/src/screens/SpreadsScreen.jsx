// tma_frontend/src/screens/SpreadsScreen.jsx

import { useState, useEffect } from "react";
import TarotCarousel from "../TarotCarousel";
import TarotCardView from "../components/TarotCardView";
import { FULL_TAROT_DECK } from "../data/tarotDeck";

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

const POSITION_LABELS = ["Прошлое", "Настоящее", "Будущее"];

// Лёгкий dev-логгер с цветами
const IS_DEV =
  typeof import.meta !== "undefined" &&
  import.meta.env &&
  import.meta.env.DEV;

function spreadsLog(level, label, payload) {
  if (!IS_DEV) return;

  const prefix = "%c[TMA:Spreads]%c " + label;
  const styleMain = "color:#8b5cf6;font-weight:bold;";
  const styleLabel = "color:#e5e7eb;";

  // level: "log" | "warn" | "error"
  const fn = console[level] || console.log;
  if (payload !== undefined) {
    fn(prefix, styleMain, styleLabel, payload);
  } else {
    fn(prefix, styleMain, styleLabel);
  }
}

export default function SpreadsScreen({
  currentSpread,
  onCreateSpread,       // (payload) => Promise<void>
  onResetCurrentSpread, // () => void
}) {
  const [spreadType, setSpreadType] = useState("one"); // "one" | "three"
  const [category, setCategory] = useState("general");
  const [customQuestion, setCustomQuestion] = useState("");
  const [useCustomQuestion, setUseCustomQuestion] = useState(false);
  const [pickedCards, setPickedCards] = useState([]); // Card[]
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const maxCards = spreadType === "one" ? 1 : 3;
  const pickedCount = pickedCards.length;

  // Сброс выбранных карт при смене типа расклада
  useEffect(() => {
    spreadsLog("log", "spreadType changed, reset pickedCards", {
      spreadType,
    });
    setPickedCards([]);
  }, [spreadType]);

  const handleChangeSpreadType = (nextType) => {
    spreadsLog("log", "handleChangeSpreadType", { nextType });
    setSpreadType(nextType);
    setError(null);

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
    if (useCustomQuestion) {
      spreadsLog("warn", "handleCategoryChange ignored (useCustomQuestion=true)", {
        nextCat,
      });
      return;
    }
    spreadsLog("log", "handleCategoryChange", { nextCat });
    setCategory(nextCat);
    setCustomQuestion("");
    setError(null);
  };

  const handleCustomQuestionChange = (e) => {
    const value = e.target.value;
    spreadsLog("log", "handleCustomQuestionChange", {
      value,
      length: value.length,
    });
    setCustomQuestion(value);
    setError(null);
  };

  const toggleUseCustomQuestion = () => {
    const next = !useCustomQuestion;
    spreadsLog("log", "toggleUseCustomQuestion", {
      prev: useCustomQuestion,
      next,
    });

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

  // Payload: интерактивный режим с выбранными картами
  const buildPayload = () => {
    const cardsCodes = pickedCards.map((c) => c.code);

    if (spreadType === "one") {
      const payload = {
        mode: "interactive",
        spread_type: "one",
        category: null, // бэк сам поставит "daily"
        question: null,
        cards: cardsCodes,
      };
      spreadsLog("log", "buildPayload (one)", payload);
      return payload;
    }

    // three-карточный расклад
    const trimmedQuestion = customQuestion.trim();

    if (useCustomQuestion) {
      const payload = {
        mode: "interactive",
        spread_type: "three",
        category: null, // при своём вопросе категорию не отправляем
        question: trimmedQuestion,
        cards: cardsCodes,
      };
      spreadsLog("log", "buildPayload (three, customQuestion)", payload);
      return payload;
    }

    // без собственного вопроса — используем категорию
    const effectiveCategory = category || "general";

    const payload = {
      mode: "interactive",
      spread_type: "three",
      category: effectiveCategory,
      question: null,
      cards: cardsCodes,
    };
    spreadsLog("log", "buildPayload (three, category)", payload);
    return payload;
  };

  const handleSubmit = async () => {
    if (!onCreateSpread || isSubmitting) {
      spreadsLog("warn", "handleSubmit skipped", {
        hasHandler: !!onCreateSpread,
        isSubmitting,
      });
      return;
    }

    // Валидация перед отправкой
    if (spreadType === "three") {
      if (useCustomQuestion) {
        if (!customQuestion.trim()) {
          const msg = "Пожалуйста, сформулируйте ваш вопрос.";
          spreadsLog("warn", "validation failed (empty customQuestion)", {
            spreadType,
            useCustomQuestion,
          });
          setError(msg);
          return;
        }
      } else {
        if (!category) {
          const msg = "Пожалуйста, выберите категорию расклада.";
          spreadsLog("warn", "validation failed (no category)", {
            spreadType,
            useCustomQuestion,
          });
          setError(msg);
          return;
        }
      }
    }

    if (pickedCards.length < maxCards) {
      const msg =
        "Сначала выберите все карты, а потом сделайте расклад.";
      spreadsLog("warn", "validation failed (not enough pickedCards)", {
        pickedLen: pickedCards.length,
        maxCards,
      });
      setError(msg);
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);

      const payload = buildPayload();
      spreadsLog("log", "handleSubmit → onCreateSpread", payload);
      await onCreateSpread(payload);
      spreadsLog("log", "handleSubmit success", {});
    } catch (e) {
      spreadsLog("error", "handleSubmit error", {
        message: e?.message,
        error: e,
      });
      console.error("[SpreadsScreen] create spread error", e);
      setError("Не удалось сделать расклад. Попробуйте ещё раз.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // onPick — сигнал "карта поймана"
  // используем pickedCards.length + 1, чтобы корректно работать
  // независимо от порядка вызова onPickCard/onPick внутри TarotCarousel
  const handlePick = () => {
    spreadsLog("log", "onPick fired", {
      pickedLen: pickedCards.length,
      maxCards,
      isSubmitting,
    });

    if (pickedCards.length + 1 >= maxCards && !isSubmitting) {
      spreadsLog("log", "onPick → handleSubmit()", {
        willSubmit: true,
      });
      void handleSubmit();
    }
  };

  const handleNewSpread = () => {
    spreadsLog("log", "handleNewSpread", {});
    onResetCurrentSpread?.();
    setError(null);
    setIsSubmitting(false);

    // Возвращаемся к дефолтным настройкам
    setSpreadType("one");
    setCategory("daily");
    setCustomQuestion("");
    setUseCustomQuestion(false);
    setPickedCards([]);
  };

  const renderPositionSummary = (cards) => {
    if (!cards || !cards.length) return null;

    if (cards.length === 1 || currentSpread?.spread_type === "one") {
      const card = cards[0];
      const name = card?.name || card?.title || "Карта дня";
      const isReversed = card?.is_reversed || card?.reversed;
      return (
        <p className="muted">
          Карта дня: {name}
          {isReversed ? " (перевернутая)" : ""}
        </p>
      );
    }

    return (
      <ul className="spread-positions-list">
        {cards.slice(0, 3).map((card, idx) => {
          const label = POSITION_LABELS[idx] || `Карта ${idx + 1}`;
          const name = card?.name || card?.title || label;
          const isReversed = card?.is_reversed || card?.reversed;
          return (
            <li key={idx} className="spread-position-row">
              <span className="muted small">{label}</span>
              <span>
                {name}
                {isReversed ? " (перевернутая)" : ""}
              </span>
            </li>
          );
        })}
      </ul>
    );
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
            deck={FULL_TAROT_DECK}
            pickedCount={pickedCount}
            maxCards={maxCards}
            onPick={handlePick}
            onPickCard={(card) => {
              spreadsLog("log", "onPickCard got card", {
                code: card?.code,
                name: card?.name,
                prevLen: pickedCards.length,
              });
              setPickedCards((prev) => [...prev, card]);
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

          {pickedCards.length > 0 && (
            <div className="picked-cards-preview">
              {pickedCards.map((card, idx) => (
                <TarotCardView
                  key={card.code + "-" + idx}
                  card={card}
                  positionLabel={
                    maxCards === 1
                      ? "Карта дня"
                      : POSITION_LABELS[idx] || `Карта ${idx + 1}`
                  }
                />
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <div className="actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSubmit}
              disabled={isSubmitting || pickedCards.length < maxCards}
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
          {renderPositionSummary(cards)}
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
