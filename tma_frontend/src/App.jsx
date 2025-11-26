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

import BottomNav from "./BottomNav";
import HomeScreen from "./screens/HomeScreen";
import SpreadsScreen from "./screens/SpreadsScreen";
import HistoryScreen from "./screens/HistoryScreen";
import ProfileScreen from "./screens/ProfileScreen";

// Форматирование красивых дат
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
  // Тема приложения
  const [theme, setTheme] = useState(() => {
    if (typeof window === "undefined") return "dark";
    return localStorage.getItem("tma_theme") || "dark"; // "dark" | "light" | "system"
  });

  // Активная вкладка (нижняя навигация)
  const [activeTab, setActiveTab] = useState("home"); // "home" | "spreads" | "history" | "profile"

  // Профиль, расклады, текущий расклад
  const [profile, setProfile] = useState(null);
  const [spreads, setSpreads] = useState({ items: [] });
  const [currentSpread, setCurrentSpread] = useState(null);

  // Общие статусы
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState(null);

  // Параметры расклада
  const [spreadType, setSpreadType] = useState("three"); // "one" | "three" | ...
  const [category, setCategory] = useState("love");
  const [question, setQuestion] = useState("");

  // Выбранные карты (индексы 0–77)
  const [selectedCards, setSelectedCards] = useState([]); // массив индексов

  // Q&A под раскладом
  const [questions, setQuestions] = useState([]);
  const [newQuestion, setNewQuestion] = useState("");
  const [questionsLoading, setQuestionsLoading] = useState(false);
  const [questionsError, setQuestionsError] = useState("");

  // Лог initData один раз
  useEffect(() => {
    console.log("InitData in window.__tma:", window.__tma?.initData);
  }, []);

  // Применение темы к document.documentElement
  useEffect(() => {
    let applied = theme;
    if (theme === "system" && typeof window !== "undefined") {
      const prefersDark = window.matchMedia?.(
        "(prefers-color-scheme: dark)"
      ).matches;
      applied = prefersDark ? "dark" : "light";
    }
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-theme", applied);
    }
    if (typeof window !== "undefined") {
      localStorage.setItem("tma_theme", theme);
    }
  }, [theme]);

  // Первичная загрузка профиля и истории раскладов
  useEffect(() => {
    async function loadInitial() {
      try {
        setError(null);

        const [profileData, spreadsData] = await Promise.all([
          fetchProfile(),
          fetchSpreads(),
        ]);

        setProfile(profileData);

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

  // Загрузка вопросов для расклада
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

  // Смена типа расклада — сбрасываем выбранные карты
  function handleSpreadTypeChange(type) {
    setSpreadType(type);
    setSelectedCards([]);
  }

  // Выбор карты (индекс 0–77)
  function handleSelectCard(index) {
    setSelectedCards((prev) => {
      const maxCards = spreadType === "one" ? 1 : 3;
      if (prev.length >= maxCards) return prev; // не больше лимита
      if (prev.includes(index)) return prev; // без дублей
      return [...prev, index];
    });
  }

  // Создание расклада (обобщённый handleCreateSpread)
  async function handleCreateSpread() {
    try {
      setLoading(true);
      setError(null);

      const payload = {
        spread_type: spreadType,
        category,
        mode: "auto", // пока авто, позже можно разделить на auto/manual
        question: question.trim() || null,
        // selected_cards: selectedCards, // можно добавить позже, когда бек будет готов
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

      // подгружаем вопросы
      await loadQuestionsForSpread(spread.id);

      // сброс вопроса и выбранных карт после успешного создания
      setQuestion("");
      setSelectedCards([]);
      setNewQuestion("");

      // переход на экран раскладов
      setActiveTab("spreads");
    } catch (err) {
      setError(err.message || "Не удалось создать расклад");
    } finally {
      setLoading(false);
    }
  }

  // Обновление профиля (бизнес-логика, UI в ProfileScreen)
  async function handleUpdateProfile(payload) {
    try {
      setLoading(true);
      setError(null);

      const updatedProfile = await updateProfile(payload);

      setProfile(updatedProfile);

      setError("Профиль сохранён");
      setTimeout(() => setError(null), 2000);
    } catch (err) {
      setError(err.message || "Не удалось обновить профиль");
    } finally {
      setLoading(false);
    }
  }

  // Ввод нового вопроса (с очисткой ошибки)
  function handleNewQuestionChange(e) {
    setNewQuestion(e.target.value);
    if (questionsError) {
      setQuestionsError("");
    }
  }

  // Задать новый вопрос к раскладу
  async function handleAskQuestion() {
    if (!currentSpread || !newQuestion.trim()) return;
    setQuestionsError("");
    setQuestionsLoading(true);
    try {
      const created = await askSpreadQuestion(
        currentSpread.id,
        newQuestion.trim()
      );
      setQuestions((prev) => [...prev, created]);
      setNewQuestion("");
    } catch (e) {
      console.error("Failed to ask question:", e);
      setQuestionsError("Не удалось отправить вопрос. Попробуйте ещё раз.");
    } finally {
      setQuestionsLoading(false);
    }
  }

  // Выбор расклада из истории
  function handleHistorySelectSpread(id) {
    if (!spreads || !Array.isArray(spreads.items)) return;

    const found = spreads.items.find((s) => s.id === id);
    if (!found) return;

    setCurrentSpread(found);
    setActiveTab("spreads");
  }

  // Рендер активного экрана
  function renderActiveScreen() {
    switch (activeTab) {
      case "home":
        return (
          <HomeScreen
            profile={profile}
            initialLoading={initialLoading}
            onGoSpreads={() => setActiveTab("spreads")}
            onGoHistory={() => setActiveTab("history")}
            onGoProfile={() => setActiveTab("profile")}
          />
        );
      case "spreads":
        return (
          <SpreadsScreen
            profile={profile}
            loading={loading}
            currentSpread={currentSpread}
            // параметры расклада
            spreadType={spreadType}
            onSpreadTypeChange={handleSpreadTypeChange}
            category={category}
            onCategoryChange={setCategory}
            question={question}
            onQuestionChange={setQuestion}
            // выбор карт
            selectedCards={selectedCards}
            onSelectCard={handleSelectCard}
            // создание расклада
            onCreateSpread={handleCreateSpread}
            // Q&A
            questions={questions}
            newQuestion={newQuestion}
            onNewQuestionChange={handleNewQuestionChange}
            questionsLoading={questionsLoading}
            questionsError={questionsError}
            onAskQuestion={handleAskQuestion}
            formatDate={formatDate}
          />
        );
      case "history":
        return (
          <HistoryScreen
            spreads={spreads?.items || []}
            initialLoading={initialLoading}
            formatDate={formatDate}
            onSelectSpread={handleHistorySelectSpread}
          />
        );
      case "profile":
        return (
          <ProfileScreen
            profile={profile}
            loading={loading}
            onUpdateProfile={handleUpdateProfile}
            theme={theme}
            onThemeChange={setTheme}
          />
        );
      default:
        return null;
    }
  }

  return (
    <div className={`app-root theme-${theme}`}>
      {/* Глобальные ошибки/статусы */}
      {error && <div className="alert alert-error">{error}</div>}
      {questionsError && (
        <div className="alert alert-error">{questionsError}</div>
      )}

      <main className="app-main">{renderActiveScreen()}</main>

      <BottomNav activeTab={activeTab} onChange={setActiveTab} />
    </div>
  );
}

export default App;
