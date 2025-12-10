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
  const [phase, setPhase] = useState("picking");      // "picking" | "result"

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const maxCards = spreadType === "one" ? 1 : 3;
  const pickedCount = pickedCards.length;

  // Колода для picker — берём как есть
  const pickerDeck = FULL_TAROT_DECK;

  if (IS_DEV) {
    console.log("[Spreads] pickerDeck meta", {
      isArray: Array.isArray(pickerDeck),
      length: Array.isArray(pickerDeck) ? pickerDeck.length : 0,
    });
  }

  // Сброс выбранных карт при смене типа расклада
  useEffect(() => {
    spreadsLog("log", "spreadType changed, reset pickedCards", {
      spreadType,
    });
    setPickedCards([]);
  }, [spreadType]);

  // Синхронизация phase с currentSpread от родителя
  useEffect(() => {
    if (currentSpread) {
      setPhase("result");
    } else {
      setPhase("picking");
    }
  }, [currentSpread]);

  const handleChangeSpreadType = (nextType) => {
    spreadsLog("log", "handleChangeSpreadType", { nextType });
    setSpreadType(nextType);
    setError(null);

    if (nextType === "one") {
      setCategory("daily");
      setCustomQuestion("");
      setUseCustomQuestion(false);
    } else {
      setCategory("general");
      setCustomQuestion("");
      setUseCustomQuestion(false);
    }
  };

  const handleCategoryChange = (nextCat) => {
    if (useCustomQuestion) {
      spreadsLog(
        "warn",
        "handleCategoryChange ignored (useCustomQuestion=true)",
        { nextCat }
      );
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
    // 1) Собираем коды карт и жёстко строкифицируем
    const cardCodes = pickedCards.map((c) => {
      if (c == null || c.code == null) return null;
      return String(c.code); // бэк всегда ждёт строки
    });

    // 2) Чистим: только непустые строки
    const cleanedCardCodes = cardCodes.filter(
      (code) => typeof code === "string" && code.trim() !== ""
    );

    // 3) Dev-лог, что реально уходит
    if (IS_DEV) {
      console.log("[Spreads] interactive payload (raw)", {
        spreadType,
        useCustomQuestion,
        category,
        customQuestion,
        cardsRaw: cardCodes,
        cardsClean: cleanedCardCodes,
        rawPickedCards: pickedCards,
      });
    }

    // 4) Жёстко проверяем количество карт
    if (cleanedCardCodes.length !== maxCards) {
      spreadsLog("warn", "cleanedCardCodes length mismatch", {
        maxCards,
        rawLen: cardCodes.length,
        cleanLen: cleanedCardCodes.length,
      });
      setError(
        "Кажется, карты выбраны некорректно. Попробуйте ещё раз."
      );
      return null;
    }

    // 5) Собираем payload под разные типы расклада
    if (spreadType === "one") {
      const payload = {
        mode: "interactive",
        spread_type: "one",
        category: null, // бэк сам поставит "daily"
        question: null,
        cards: cleanedCardCodes,
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
        category: null,
        question: trimmedQuestion,
        cards: cleanedCardCodes,
      };
      spreadsLog("log", "buildPayload (three, customQuestion)", payload);
      return payload;
    }

    const effectiveCategory = category || "general";

    const payload = {
      mode: "interactive",
      spread_type: "three",
      category: effectiveCategory,
      question: null,
      cards: cleanedCardCodes,
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

    setError(null);

    // 1) Базовые проверки по количеству карт
    if (pickedCards.length !== maxCards) {
      const msg = "Нужно выбрать все карты перед раскладом.";
      spreadsLog("warn", "validation failed (picked != maxCards)", {
        pickedLen: pickedCards.length,
        maxCards,
      });
      setError(msg);
      return;
    }

    // 2) Вопрос/категория для трёх карт
    if (spreadType === "three") {
      if (useCustomQuestion) {
        if (!customQuestion.trim()) {
          const msg = "Пожалуйста, сформулируйте ваш вопрос.";
          spreadsLog(
            "warn",
            "validation failed (empty customQuestion)",
            { spreadType, useCustomQuestion }
          );
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

    // 3) Сбор payload
    const payload = buildPayload();
    if (!payload) {
      spreadsLog(
        "warn",
        "handleSubmit aborted: buildPayload returned null",
        {}
      );
      return;
    }

    // 4) Отправка на бэк через onCreateSpread (API живёт в App)
    try {
      setIsSubmitting(true);
      spreadsLog("log", "handleSubmit → onCreateSpread", payload);
      await onCreateSpread(payload);
      spreadsLog("log", "handleSubmit success", {});
      setPhase("result"); // после успешного ответа переходим в фазу результата
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

  const handleNewSpread = () => {
    spreadsLog("log", "handleNewSpread", {});
    onResetCurrentSpread?.();
    setError(null);
    setIsSubmitting(false);

    setPhase("picking");
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

  return (
    <div className="page page-spreads">
      <h2 className="section-title">Расклады Таро</h2>

      {/* Фаза выбора карт и параметров расклада */}
      {phase === "picking" && (
        <>
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
                  «Прошлое / Настоящее / Будущее» — три карты, которые
                  показывают динамику ситуации.
                </p>
              )}
            </div>

            {spreadType === "three" && (
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
                  <label className="field-label">
                    Свой вопрос вместо категории
                  </label>
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

            {spreadType !== "three" && (
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
              deck={pickerDeck}
              pickedCount={pickedCount}
              maxCards={maxCards}
              onPickCard={(card) => {
                spreadsLog("log", "onPickCard got card", {
                  code: card?.code,
                  name: card?.name,
                  prevLen: pickedCards.length,
                });
                setPickedCards((prev) => {
                  if (prev.length >= maxCards) return prev;
                  if (prev.some((c) => c.code === card.code)) return prev;
                  return [...prev, card];
                });
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
              <div className="picked-cards-strip">
                {pickedCards.map((card, index) => (
                  <TarotCardView
                    key={card.code || `${card.id}-${index}`}
                    card={card}
                    positionLabel={
                      spreadType === "three"
                        ? index === 0
                          ? "Прошлое"
                          : index === 1
                          ? "Настоящее"
                          : "Будущее"
                        : undefined
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
                disabled={
                  isSubmitting || pickedCards.length !== maxCards
                }
              >
                {isSubmitting
                  ? "Ответ в процессе, ожидайте…"
                  : "Сделать расклад"}
              </button>
            </div>
          </div>
        </>
      )}

      {/* Фаза результата: показываем только текущий расклад */}
      {phase === "result" && currentSpread && (
        <div className="card">
          <div className="spread-header">
            <div className="spread-title">
              {getSpreadTitle(currentSpread.spread_type)}
            </div>
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
              selectedCards={currentSpread.cards || []}
              maxCards={currentSpread.spread_type === "one" ? 1 : 3}
            />
          </div>

          <div className="spread-interpretation">
            {renderPositionSummary(currentSpread.cards || [])}
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
      )}

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
