// src/App.jsx
import React, { useEffect, useState } from "react";
import {
  fetchProfile,
  fetchSpreads,
  createAutoSpread,
  updateProfile,
  fetchSpreadQuestions,
  askSpreadQuestion,
} from "./api/client";

// ——— Форматирование красивых дат ———
function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function App() {
  const [profile, setProfile] = useState(null);
  const [spreads, setSpreads] = useState({ items: [] });
  const [currentSpread, setCurrentSpread] = useState(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState(null);

  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [profileForm, setProfileForm] = useState({
    birth_date: "",
    gender: "",
  });

  const [activeTab, setActiveTab] = useState("main");
  const [question, setQuestion] = useState("");

  // Q&A под раскладом
  const [questions, setQuestions] = useState([]);
  const [newQuestion, setNewQuestion] = useState("");
  const [questionsLoading, setQuestionsLoading] = useState(false);
  const [questionsError, setQuestionsError] = useState("");

  // ——— Лог initData только один раз ———
  useEffect(() => {
    console.log("InitData in window.__tma:", window.__tma?.initData);
  }, []);

  // ——— Первичная загрузка ———
  useEffect(() => {
    async function loadInitial() {
      try {
        setError(null);

        const [profileData, spreadsData] = await Promise.all([
          fetchProfile(),
          fetchSpreads(),
        ]);

        setProfile(profileData);

        if (profileData) {
          setProfileForm({
            birth_date: profileData.birth_date || "",
            gender: profileData.gender || "",
          });
        }

        if (spreadsData && Array.isArray(spreadsData.items)) {
          setSpreads({ items: spreadsData.items });
        }
      } catch (e) {
        setError(e.message || "Ошибка загрузки");
      } finally {
        setInitialLoading(false);
      }
    }

    loadInitial();
  }, []);

  // ——— Загрузка вопросов для расклада ———
  async function loadQuestionsForSpread(spreadId) {
    if (!spreadId) {
      setQuestions([]);
      return;
    }
    setQuestionsError("");
    setQuestionsLoading(true);
    try {
      const qs = await fetchSpreadQuestions(spreadId);
      setQuestions(qs?.items || []);
    } catch (e) {
      console.error("Failed to load questions:", e);
      setQuestionsError("Не удалось загрузить вопросы к раскладу.");
    } finally {
      setQuestionsLoading(false);
    }
  }

  // ——— Создание авто-расклада ———
  async function handleCreateAutoSpread() {
    try {
      setLoading(true);
      setError(null);

      const payload = {
        spread_type: "three",
        category: "love",
        mode: "auto",
        question: question.trim() || null,
      };

      const spread = await createAutoSpread(payload);

      const spreadWithQuestion = {
        ...spread,
        question: payload.question || null,
      };

      setCurrentSpread(spreadWithQuestion);

      setSpreads((prev) => {
        const items = prev?.items ?? [];
        const newItem = {
          id: spread.id,
          spread_type: spread.spread_type,
          category: spread.category,
          created_at: spread.created_at,
          short_preview:
            spread.interpretation ||
            "Интерпретация ещё генерируется или не задана",
          has_questions: !!payload.question,
        };
        return { ...prev, items: [newItem, ...items] };
      });

      // после выбора/создания расклада подгружаем вопросы
      loadQuestionsForSpread(spread.id);

      setQuestion("");
    } catch (err) {
      setError(err.message || "Не удалось создать расклад");
    } finally {
      setLoading(false);
    }
  }

  // ——— Профиль: начало редактирования ———
  function handleProfileEditToggle() {
    if (profile) {
      setProfileForm({
        birth_date: profile.birth_date || "",
        gender: profile.gender || "",
      });
    }
    setIsEditingProfile(true);
  }

  // ——— Профиль: изменение формы ———
  function handleProfileFormChange(event) {
    const { name, value } = event.target;
    setProfileForm((prev) => ({ ...prev, [name]: value }));
  }

  // ——— Профиль: сохранить ———
  async function handleProfileSave() {
    try {
      setLoading(true);
      setError(null);

      const payload = {
        birth_date: profileForm.birth_date || null,
        gender: profileForm.gender || null,
      };

      const updatedProfile = await updateProfile(payload);

      setProfile(updatedProfile);
      setIsEditingProfile(false);

      setError("Профиль сохранён");
      setTimeout(() => setError(null), 2000);
    } catch (err) {
      setError(err.message || "Не удалось обновить профиль");
    } finally {
      setLoading(false);
    }
  }

  // ——— Профиль: отмена редактирования ———
  function handleProfileCancel() {
    if (profile) {
      setProfileForm({
        birth_date: profile.birth_date || "",
        gender: profile.gender || "",
      });
    }
    setIsEditingProfile(false);
  }

  // ——— Ввод нового вопроса (с очисткой ошибки) ———
  function handleNewQuestionChange(e) {
    setNewQuestion(e.target.value);
    if (questionsError) {
      setQuestionsError("");
    }
  }

  // ——— Задать новый вопрос к раскладу ———
  async function handleAskQuestion() {
    if (!currentSpread || !newQuestion.trim()) return;
    setQuestionsError("");
    setQuestionsLoading(true);
    try {
      const created = await askSpreadQuestion(
        currentSpread.id,
        newQuestion.trim()
      );
      // optimistic update: добавляем в конец списка, не трогая остальные
      setQuestions((prev) => [...prev, created]);
      setNewQuestion("");
    } catch (e) {
      console.error("Failed to ask question:", e);
      setQuestionsError("Не удалось отправить вопрос. Попробуйте ещё раз.");
    } finally {
      setQuestionsLoading(false);
    }
  }

  return (
    <div className="app-root">
      <h1>Luna Tarot TMA (dev)</h1>

      {/* ——— Блок ошибок / статусов ——— */}
      {error && <div className="alert alert-error">{error}</div>}
      {questionsError && (
        <div className="alert alert-error">{questionsError}</div>
      )}

      {/* ——— Таббар ——— */}
      <div className="tabs">
        <button
          className={activeTab === "main" ? "tab active" : "tab"}
          onClick={() => setActiveTab("main")}
        >
          Главная
        </button>

        <button
          className={activeTab === "profile" ? "tab active" : "tab"}
          onClick={() => setActiveTab("profile")}
        >
          Профиль
        </button>
      </div>

      {/* ————————————————————————
          ВКЛАДКА: ГЛАВНАЯ
      ———————————————————————— */}
      {activeTab === "main" && (
        <>
          {/* Новый расклад */}
          <div className="block">
            <h2>Новый расклад</h2>

            <label className="field-label">Вопрос (необязательно)</label>
            <textarea
              className="text-input"
              rows={3}
              placeholder="О чём вы хотите спросить карты?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />

            <button onClick={handleCreateAutoSpread} disabled={loading}>
              {loading
                ? "Создаём расклад..."
                : "Создать авто-расклад (3 карты, любовь)"}
            </button>
          </div>

          {/* Текущий расклад */}
          <div className="block">
            <h2>Текущий расклад</h2>

            {!currentSpread && <p>Пока расклад не создан.</p>}

            {currentSpread && (
              <div className="spread">
                <p>
                  <strong>ID:</strong> {currentSpread.id}
                </p>

                {currentSpread.question && (
                  <div style={{ marginBottom: 8 }}>
                    <div className="field-label">Вопрос к раскладу</div>
                    <div>{currentSpread.question}</div>
                  </div>
                )}

                <p>
                  <strong>Тип:</strong> {currentSpread.spread_type}
                </p>
                <p>
                  <strong>Категория:</strong> {currentSpread.category}
                </p>
                <p>
                  <strong>Создан:</strong>{" "}
                  {formatDate(currentSpread.created_at)}
                </p>

                {Array.isArray(currentSpread.cards) && (
                  <>
                    <h3>Карты</h3>
                    <ul>
                      {currentSpread.cards.map((card) => (
                        <li key={card.position}>
                          <strong>{card.position}.</strong> {card.name}
                          {card.is_reversed ? " — (перевёрнутая)" : ""}
                        </li>
                      ))}
                    </ul>
                  </>
                )}

                <h3>Интерпретация</h3>
                {currentSpread.interpretation ? (
                  <p>{currentSpread.interpretation}</p>
                ) : (
                  <p>Интерпретация ещё генерируется или не задана.</p>
                )}
              </div>
            )}

            {/* Вопросы к раскладу (Q&A) */}
            <div className="block" style={{ marginTop: "1rem" }}>
              <div className="block-title">Вопросы к раскладу</div>

              {!currentSpread ? (
                <p className="text-muted">
                  Сначала создайте расклад, чтобы задать уточняющий вопрос.
                </p>
              ) : (
                <>
                  {questionsLoading && (
                    <div className="text-muted">Загрузка вопросов...</div>
                  )}

                  {!questionsLoading && questions.length === 0 && (
                    <div className="text-muted">
                      Пока вопросов нет. Вы можете задать первый.
                    </div>
                  )}

                  {!questionsLoading && questions.length > 0 && (
                    <ul className="questions-list">
                      {questions.map((q) => (
                        <li key={q.id} className="question-item">
                          <div className="question-text">❓ {q.question}</div>
                          {q.answer && (
                            <div className="answer-text">✨ {q.answer}</div>
                          )}
                          <div className="question-date">
                            {formatDate(q.created_at)}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}

                  {/* Форма задать новый вопрос */}
                  <div
                    className="question-form"
                    style={{ marginTop: "0.75rem" }}
                  >
                    <div className="field-label">Новый вопрос к раскладу</div>
                    <textarea
                      className="text-input"
                      rows={3}
                      placeholder="Что ещё хотите уточнить по этому раскладу?"
                      value={newQuestion}
                      onChange={handleNewQuestionChange}
                    />
                    <button
                      type="button"
                      disabled={
                        questionsLoading ||
                        !currentSpread ||
                        !newQuestion.trim()
                      }
                      onClick={handleAskQuestion}
                    >
                      {questionsLoading ? "Отправка..." : "Задать вопрос"}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* История раскладов */}
          <div className="block">
            <h2>История раскладов</h2>

            {initialLoading && !spreads.items.length && (
              <p>Загрузка истории...</p>
            )}

            {!initialLoading && spreads.items.length === 0 && (
              <p>История раскладов пуста.</p>
            )}

            {spreads.items.length > 0 && (
              <ul>
                {spreads.items.slice(0, 5).map((s) => (
                  <li key={s.id} style={{ marginBottom: "0.75rem" }}>
                    <div>
                      <strong>#{s.id}</strong> • {s.spread_type} • {s.category} •{" "}
                      {formatDate(s.created_at)} {s.has_questions && "💬"}
                    </div>

                    {s.short_preview && (
                      <div style={{ opacity: 0.7, fontSize: "0.9em" }}>
                        Интерпретация расклада: {s.short_preview}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Dev-информация */}
          {import.meta.env.VITE_TMA_DEV_MODE === "1" && (
            <div
              style={{
                marginTop: "2rem",
                fontSize: "0.75rem",
                opacity: 0.6,
                borderTop: "1px solid #444",
                paddingTop: "0.5rem",
              }}
            >
              Dev mode: VITE_TMA_DEV_MODE=1
              <br />
              API_BASE_URL: {import.meta.env.VITE_API_BASE_URL}
            </div>
          )}
        </>
      )}

      {/* ————————————————————————
          ВКЛАДКА: ПРОФИЛЬ
      ———————————————————————— */}
      {activeTab === "profile" && (
        <div className="block">
          <h2>Профиль</h2>

          {initialLoading && !profile && <p>Загрузка профиля...</p>}
          {!initialLoading && !profile && <p>Профиль не загружен.</p>}

          {profile && (
            <>
              {!isEditingProfile ? (
                <>
                  <p>Telegram ID: {profile.user_id}</p>
                  <p>Username: {profile.username || "—"}</p>
                  <p>
                    Имя:{" "}
                    {[profile.first_name, profile.last_name]
                      .filter(Boolean)
                      .join(" ") || "—"}
                  </p>
                  <p>Дата рождения: {profile.birth_date || "—"}</p>
                  <p>
                    Пол:{" "}
                    {profile.gender === "female"
                      ? "женский"
                      : profile.gender === "male"
                      ? "мужской"
                      : "—"}
                  </p>
                  <p>Знак зодиака: {profile.zodiac || "—"}</p>
                  <p>Возраст: {profile.age ?? "—"}</p>

                  <button onClick={handleProfileEditToggle} disabled={loading}>
                    Редактировать профиль
                  </button>
                </>
              ) : (
                <>
                  <label>
                    Дата рождения:
                    <input
                      type="date"
                      name="birth_date"
                      value={profileForm.birth_date || ""}
                      onChange={handleProfileFormChange}
                    />
                  </label>

                  <label>
                    Пол:
                    <select
                      name="gender"
                      value={profileForm.gender || ""}
                      onChange={handleProfileFormChange}
                    >
                      <option value="">Не выбран</option>
                      <option value="female">Женский</option>
                      <option value="male">Мужской</option>
                      <option value="other">Другое</option>
                    </select>
                  </label>

                  <div style={{ marginTop: "0.75rem", display: "flex", gap: 8 }}>
                    <button onClick={handleProfileSave} disabled={loading}>
                      Сохранить
                    </button>
                    <button onClick={handleProfileCancel} disabled={loading}>
                      Отмена
                    </button>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default App;
