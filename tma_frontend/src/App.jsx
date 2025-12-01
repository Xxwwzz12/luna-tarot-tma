// src/App.jsx
import React, { useEffect, useState } from "react";
import {
  apiGet,
  apiPost,
  fetchSpreadQuestions,
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

  // Профиль пользователя
  const [profile, setProfile] = useState(null);

  // История раскладов (список)
  const [spreads, setSpreads] = useState({ items: [] });

  // Текущий расклад (detail или элемент из списка)
  // currentSpread.cards — карты расклада с бэка (viewer-карусель).
  const [currentSpread, setCurrentSpread] = useState(null);

  // AI-интерпретация расклада
  const [isInterpreting, setIsInterpreting] = useState(false);

  // Состояние Q&A для текущего расклада
  const [qaState, setQaState] = useState({
    question: "",
    isAsking: false,
    answer: null,
  });

  // Общие статусы
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState(null);

  // Параметры расклада
  const [spreadType, setSpreadType] = useState("three"); // "one" | "three"
  const [category, setCategory] = useState("love");
  const [question, setQuestion] = useState("");

  // Выбранные карты в режиме picker (фронтовый ритуал, не уходит на бэк)
  const [selectedCards, setSelectedCards] = useState([]);

  // История вопросов/ответов (старый Q&A-список, пока оставляем)
  const [questions, setQuestions] = useState([]);
  const [newQuestion, setNewQuestion] = useState("");
  const [questionsLoading, setQuestionsLoading] = useState(false);
  const [questionsError, setQuestionsError] = useState(false);

  // Лог initData один раз (диагностика)
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

  // Загрузка профиля
  async function fetchProfile() {
    console.log("[TMA] API GET /profile");
    const res = await apiGet("/profile");

    if (res?.ok && res.data) {
      console.log("[TMA] Raw profile from API:", res.data);
      setProfile(res.data);
      console.log("[TMA] Profile loaded:", {
        user_id: res.data.user_id,
        username: res.data.username,
      });
    } else {
      console.warn("[TMA] Failed to load profile", res);
      setProfile(null);
    }
  }

  // Загрузка истории раскладов
  async function fetchSpreadsList(page = 1, limit = 10) {
    console.log(
      "[TMA] API GET /spreads?page=%s&limit=%s",
      page,
      limit
    );
    const res = await apiGet(`/spreads?page=${page}&limit=${limit}`);

    if (res?.ok && res.data && Array.isArray(res.data.items)) {
      setSpreads(res.data);
      console.log(
        "[TMA] Spreads list loaded:",
        res.data.items.length,
        "items"
      );
    } else {
      console.warn("[TMA] Spreads list is empty or invalid.", res);
      setSpreads(null);
    }
  }

  // Первичная загрузка профиля и истории
  useEffect(() => {
    (async () => {
      try {
        setError(null);
        console.log(
          "[TMA] API_BASE_URL:",
          import.meta.env.VITE_API_BASE_URL
        );
        await Promise.all([fetchProfile(), fetchSpreadsList()]);
      } catch (e) {
        console.error("[TMA] Initial load error:", e);
        setError(e.message || "Ошибка загрузки");
      } finally {
        setInitialLoading(false);
      }
    })();
  }, []);

  // Загрузка списка вопросов для расклада
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

  // Смена типа расклада — сбрасываем визуальный выбор карт
  function handleSpreadTypeChange(type) {
    setSpreadType(type);
    setSelectedCards([]);
  }

  // Выбор карты в picker
  function handleSelectCard(card, index) {
    const maxCards = spreadType === "one" ? 1 : 3;

    setSelectedCards((prev) => {
      if (!card) return prev;

      const isDuplicate = prev.some(
        (c) =>
          c &&
          card &&
          c.id === card.id &&
          (c.position === card.position || c.position === undefined)
      );
      if (isDuplicate) return prev;

      let next = [...prev, card];
      if (next.length > maxCards) {
        next = next.slice(0, maxCards);
      }
      return next;
    });
  }

  // Создание расклада (POST /spreads) — payload приходит из SpreadsScreen
  async function handleCreateSpread(payload) {
    try {
      if (!payload) {
        console.warn("[TMA] handleCreateSpread called without payload");
        return;
      }

      setLoading(true);
      setError(null);
      setIsInterpreting(true);
      setQaState({ question: "", isAsking: false, answer: null });

      console.log("[TMA] API POST /spreads", payload);
      const res = await apiPost("/spreads", payload);

      if (res?.ok && res.data) {
        const detail = res.data; // SpreadDetail
        console.log("[TMA] New spread detail:", detail);

        setCurrentSpread(detail);
        setActiveTab("spreads");

        // Обновляем историю, если она уже загружена
        setSpreads((prev) => {
          if (!prev || !Array.isArray(prev.items)) return prev;

          const newItem = {
            id: detail.id,
            spread_type: detail.spread_type,
            category: detail.category || "general",
            created_at: detail.created_at,
            short_preview: detail.interpretation
              ? detail.interpretation.slice(0, 140).trim()
              : null,
            has_questions: false,
            interpretation: detail.interpretation || null,
          };

          return {
            ...prev,
            items: [newItem, ...prev.items],
            total_items: (prev.total_items || prev.items.length) + 1,
          };
        });

        await loadQuestionsForSpread(detail.id);

        setQuestion("");
        setSelectedCards([]);
        setNewQuestion("");
      } else {
        console.warn("[TMA] Failed to create spread", res);
        setError("Не удалось создать расклад");
      }
    } catch (err) {
      console.error("[TMA] Error in handleCreateSpread", err);
      setError(err.message || "Не удалось создать расклад");
    } finally {
      setLoading(false);
      setIsInterpreting(false);
    }
  }

  // Обновление профиля
  async function handleUpdateProfile(update) {
    console.log("[TMA] Updating profile with payload:", update);
    const res = await apiPost("/profile", update);
    console.log("[TMA] Profile updated:", res);

    if (res?.ok && res.data) {
      console.log("[TMA] New profile from API:", res.data);
      setProfile(res.data);
    }
  }

  // Изменение текста нового вопроса (старый Q&A UI)
  function handleNewQuestionChange(e) {
    setNewQuestion(e.target.value);
    if (questionsError) {
      setQuestionsError("");
    }
  }

  // Новый обработчик Q&A: handleAskQuestion(spreadId, question)
  async function handleAskQuestion(spreadId, questionText) {
    const effectiveSpreadId = spreadId ?? currentSpread?.id;
    const text = (questionText ?? newQuestion ?? "").trim();

    if (!effectiveSpreadId || !text) return;

    setQuestionsError("");
    setQuestionsLoading(true);

    setQaState({
      question: text,
      isAsking: true,
      answer: null,
    });

    try {
      const res = await apiPost(`/spreads/${effectiveSpreadId}/questions`, {
        question: text,
      });

      if (res?.ok && res.data) {
        setQaState({
          question: text,
          isAsking: false,
          answer: res.data,
        });

        // по желанию, поддерживаем список вопросов
        setQuestions((prev) => [...prev, res.data]);
        setNewQuestion("");
      } else {
        console.warn("[TMA] Failed to ask question", res);
        setQaState((prev) => ({ ...prev, isAsking: false }));
        setQuestionsError("Не удалось отправить вопрос. Попробуйте ещё раз.");
      }
    } catch (e) {
      console.error("Failed to ask question:", e);
      setQaState((prev) => ({ ...prev, isAsking: false }));
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
            // флаги состояния AI и Q&A
            isInterpreting={isInterpreting}
            qaState={qaState}
            onAskQuestion={handleAskQuestion}
            // параметры расклада
            spreadType={spreadType}
            onSpreadTypeChange={handleSpreadTypeChange}
            category={category}
            onCategoryChange={setCategory}
            question={question}
            onQuestionChange={setQuestion}
            // выбор карт (picker)
            selectedCards={selectedCards}
            onSelectCard={handleSelectCard}
            // создание расклада
            onCreateSpread={handleCreateSpread}
            // старый Q&A-список — пока тоже прокидываем
            questions={questions}
            newQuestion={newQuestion}
            onNewQuestionChange={handleNewQuestionChange}
            questionsLoading={questionsLoading}
            questionsError={questionsError}
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
