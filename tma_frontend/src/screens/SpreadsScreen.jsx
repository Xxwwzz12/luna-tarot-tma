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
  currentSpread,          // SpreadDetail | null
  onCreateSpread,         // (payload) => Promise<void> | void
  isInterpreting,         // boolean
  qaState,                // { question, isAsking, answer } | undefined
  onAskQuestion,          // (spreadId, question) => Promise<void> | void
}) {
  // Внутренние состояния экрана
  const [spreadType, setSpreadType] = useState("one");          // "one" | "three"
  const [mode, setMode] = useState("auto");                     // пока не используется, но заложен
  const [category, setCategory] = useState("daily");            // дефолт для one
  const [questionMode, setQuestionMode] = useState("category"); // "category" | "custom"
  const [userQuestion, setUserQuestion] = useState("");

  // Визуальный выбор карт (чисто фронтовый UX)
  const [pickedCards, setPickedCards] = useState([]);

  const [isQuestionFormOpen, setIsQuestionFormOpen] = useState(false);
  const [qaInput, setQaInput] = useState("");

  const trimmedUserQuestion = (userQuestion || "").trim();
  const hasQa = qaState && (qaState.question || qaState.answer);

  // Выбор карты в режиме picker
  const handleSelectCard = (cardOrIndex) => {
    // Минималистично: считаем, что TarotCarousel передаёт индекс
    // Можно усложнить позже.
    setPickedCards((prev) => {
      const exists = prev.includes(cardOrIndex);
      if (exists) {
        return prev.filter((v) => v !== cardOrIndex);
      }
      return [...prev, cardOrIndex];
    });
  };

  // Формирование payload под /spreads
  const handleSubmit = () => {
    if (isInterpreting) return;

    let payloadCategory = null;
    let payloadQuestion = null;

    if (spreadType === "one") {
      payloadCategory = "daily";
      payloadQuestion = null;
    } else {
      if (questionMode === "category") {
        payloadCategory = category || "general";
        payloadQuestion = null;
      } else {
        const q = trimmedUserQuestion || null;
        payloadCategory = null;
        payloadQuestion = q;
      }
    }

    const payload = {
      mode: mode || "auto",
      spread_type: spreadType,
      category: payloadCategory,
      question: payloadQuestion,
    };

    onCreateSpread && onCreateSpread(payload);
  };

  // дизейбл кнопки «Сделать расклад»
  const isCreateDisabled = (() => {
    if (isInterpreting) return true;

    if (spreadType === "one") {
      return false; // всегда можно сделать карту дня
    }

    // "three"
    if (questionMode === "category") {
      return !category;
    }

    // "custom"
    return !trimmedUserQuestion;
  })();

  const handleAskQuestionSubmit = () => {
    if (!currentSpread || isInterpreting || !onAskQuestion) return;

    const q = qaInput.trim();
    if (!q) return;

    onAskQuestion(currentSpread.id, q);
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

  const maxCards = spreadType === "one" ? 1 : 3;
  const pickedCount = Array.isArray(pickedCards) ? pickedCards.length : 0;

  const canShowPicker = !currentSpread;
  const canShowViewer = !!currentSpread;

  return (
    <div className="page page-spreads">
      {/* До интерпретации: выбор расклада */}
      {!currentSpread && (
        <>
          {/* Тип расклада */}
          <section className="card card-spread-type">
            <h2>Тип расклада</h2>

            <div className="pill-toggle">
              <button
                type="button"
                className={
                  spreadType === "one" ? "pill-option active" : "pill-option"
                }
                onClick={() => !isInterpreting && setSpreadType("one")}
                disabled={isInterpreting}
              >
                <span>🃏</span>
                <span>Карта дня</span>
              </button>

              <button
                type="button"
                className={
                  spreadType === "three" ? "pill-option active" : "pill-option"
                }
                onClick={() => !isInterpreting && setSpreadType("three")}
                disabled={isInterpreting}
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
                Для карты дня тема задаётся автоматически: «Что ждёт меня
                сегодня?»
              </p>
            )}

            {spreadType === "three" && (
              <>
                <div className="question-mode-toggle">
                  <button
                    type="button"
                    className={
                      questionMode === "category"
                        ? "pill-option active"
                        : "pill-option"
                    }
                    onClick={() =>
                      !isInterpreting && setQuestionMode("category")
                    }
                    disabled={isInterpreting}
                  >
                    По категориям
                  </button>
                  <button
                    type="button"
                    className={
                      questionMode === "custom"
                        ? "pill-option active"
                        : "pill-option"
                    }
                    onClick={() =>
                      !isInterpreting && setQuestionMode("custom")
                    }
                    disabled={isInterpreting}
                  >
                    Свой вопрос
                  </button>
                </div>

                {questionMode === "category" && (
                  <div className="chip-row">
                    {CATEGORY_OPTIONS.filter(
                      (opt) => opt.code !== "daily" // daily только для one
                    ).map((opt) => (
                      <button
                        key={opt.code}
                        type="button"
                        className={
                          category === opt.code
                            ? "chip chip-active"
                            : "chip"
                        }
                        onClick={() =>
                          !isInterpreting && setCategory(opt.code)
                        }
                        disabled={isInterpreting}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                )}

                {questionMode === "custom" && (
                  <div className="field">
                    <label
                      htmlFor="spread-user-question"
                      className="field-label"
                    >
                      Ваш вопрос
                    </label>
                    <textarea
                      id="spread-user-question"
                      className="textarea"
                      rows={3}
                      value={userQuestion}
                      onChange={(e) =>
                        !isInterpreting && setUserQuestion(e.target.value)
                      }
                      placeholder="Например: «Что ждёт меня в ближайшие полгода в работе?»"
                      disabled={isInterpreting}
                    />
                  </div>
                )}
              </>
            )}
          </section>

          {/* Выбор карт — режим picker */}
          {canShowPicker && (
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

              <p className="muted">
                Выбрано: {pickedCount} / {maxCards}
              </p>
            </section>
          )}

          {/* Кнопка создания расклада */}
          <section className="card card-actions">
            <button
              type="button"
              className="btn-primary"
              disabled={isCreateDisabled}
              onClick={handleSubmit}
            >
              Сделать расклад
            </button>

            <p className="muted small">
              Сейчас карты выбираются автоматически. Визуальный выбор через
              карусель появится позже.
            </p>
          </section>
        </>
      )}

      {/* После интерпретации: просмотр расклада + Q&A */}
      {canShowViewer && (
        <section className="card section spread-current">
          <div className="spread-current-header">
            <p className="section-title">Текущий расклад</p>
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

          {currentSpread.interpretation && (
            <div className="spread-interpretation">
              <p className="section-subtitle">Интерпретация</p>
              <p className="interpretation-text">
                {currentSpread.interpretation}
              </p>
            </div>
          )}

          {/* Блок доп. вопросов по раскладу */}
          <div className="spread-qa">
            <button
              type="button"
              className="btn-secondary"
              onClick={() =>
                !isInterpreting &&
                setIsQuestionFormOpen((prev) => !prev)
              }
              disabled={isInterpreting}
            >
              Задать вопрос по раскладу
            </button>

            {isQuestionFormOpen && (
              <div className="card card-qa">
                <div className="field">
                  <label htmlFor="qa-question" className="field-label">
                    Ваш уточняющий вопрос
                  </label>
                  <textarea
                    id="qa-question"
                    className="textarea"
                    rows={3}
                    value={qaInput}
                    onChange={(e) => setQaInput(e.target.value)}
                    placeholder="Например: «Что мне важно учесть в ближайший месяц?»"
                    disabled={isInterpreting || qaState?.isAsking}
                  />
                </div>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={handleAskQuestionSubmit}
                  disabled={
                    isInterpreting ||
                    qaState?.isAsking ||
                    !qaInput.trim()
                  }
                >
                  Отправить вопрос
                </button>
              </div>
            )}

            {hasQa && (
              <div className="qa-answer">
                {qaState?.question && (
                  <p className="qa-question">
                    <span className="muted small">Ваш вопрос:</span>{" "}
                    {qaState.question}
                  </p>
                )}
                {qaState?.answer && (
                  <p className="qa-answer-text">
                    <span className="muted small">Ответ:</span>{" "}
                    {qaState.answer}
                  </p>
                )}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Оверлей ожидания интерпретации */}
      {isInterpreting && (
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
