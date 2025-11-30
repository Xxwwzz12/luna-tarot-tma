// src/App.jsx
import React, { useEffect, useState } from "react";
import {
  apiGet,
  apiPost,
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

  // Профиль пользователя
  const [profile, setProfile] = useState(null);

  // История раскладов (список)
  const [spreads, setSpreads] = useState({ items: [] });

  // Текущий расклад (detail или элемент из списка)
  // Важно: currentSpread намеренно НЕ сбрасывается при смене вкладок —
  // чтобы можно было вернуться к уже открытому раскладу.
  // currentSpread.cards — это «истинные» карты расклада с бэка (viewer-карусель).
  const [currentSpread, setCurrentSpread] = useState(null);

  // Общие статусы
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState(null);

  // Параметры расклада
  const [spreadType, setSpreadType] = useState("three"); // "one" | "three" | ...
  const [category, setCategory] = useState("love");
  const [question, setQuestion] = useState("");

  // Выбранные карты пользователем в режиме picker (TarotCarousel-пикер).
  // Это чисто фронтовый ритуал: POST /spreads от них не зависит.
  // Здесь храним объекты карт (минимум: { id, position, ... }).
  const [selectedCards, setSelectedCards] = useState([]);

  // Q&A под раскладом
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

  // Загрузка профиля с правильной распаковкой APIResponse
  async function fetchProfile() {
    console.log("[TMA] API GET /profile");
    const res = await apiGet("/profile");

    if (res?.ok && res.data) {
      console.log("[TMA] Raw profile from API:", res.data); // доп. лог структуры профиля
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

  // Загрузка истории раскладов с правильной распаковкой APIResponse
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

  // Первичная загрузка профиля и истории раскладов
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

  // Смена типа расклада — сбрасываем выбранные карты (picker)
  function handleSpreadTypeChange(type) {
    setSpreadType(type);
    setSelectedCards([]);
  }

  // Выбор карты в режиме picker.
  // Сигнатура под TarotCarousel: onSelectCard(card, index).
  // selectedCards — это "выбор пользователя", никак не влияет на backend.
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

  // Создание расклада (POST /спreads) — payload приходит из SpreadsScreen
  async function handleCreateSpread(payload) {
    try {
      if (!payload) {
        console.warn("[TMA] handleCreateSpread called without payload");
        return;
      }

      setLoading(true);
      setError(null);

      console.log("[TMA] API POST /spreads", payload);
      const res = await apiPost("/spreads", payload);

      if (res?.ok && res.data) {
        const detail = res.data; // SpreadDetail от бэка

        setCurrentSpread(detail);
        setActiveTab("spreads");

        // Обновляем историю в памяти, если уже загружена
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
    }
  }

  // Обновление профиля — через APIResponse { ok, data, error }
  async function handleUpdateProfile(update) {
    try {
      console.log("[TMA] Updating profile with payload:", update);
      const res = await apiPost("/profile", update);
      console.log("[TMA] Profile updated:", res);

      if (res?.ok && res.data) {
        setProfile(res.data);
      }
    } catch (err) {
      console.error("[TMA] Failed to update profile", err);
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
            // выбор карт (picker)
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
            profile={profile} // ВАЖНО: без .data, сюда летит уже res.data
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
