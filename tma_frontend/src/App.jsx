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
  const [spreads, setSpreads] = useState(null);

  // Текущий расклад для вкладки "Расклады"
  const [currentSpread, setCurrentSpread] = useState(null);

  // Детальный расклад для вкладки "История"
  const [historyDetail, setHistoryDetail] = useState(null);

  // AI-интерпретация текущего расклада
  const [isInterpreting, setIsInterpreting] = useState(false);

  // Состояние Q&A под текущим раскладом (для SpreadsScreen)
  const [qaState, setQaState] = useState({
    question: "",
    isAsking: false,
    answer: null,
  });

  // Флаг отправки вопроса для истории
  const [isAskingQuestion, setIsAskingQuestion] = useState(false);

  // Общие статусы
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState(null);

  // Параметры расклада
  const [spreadType, setSpreadType] = useState("three"); // "one" | "three"
  const [category, setCategory] = useState("love");
  const [question, setQuestion] = useState("");

  // Выбранные карты в режиме picker (фронтовый ритуал)
  const [selectedCards, setSelectedCards] = useState([]);

  // Старый список Q&A для текущего расклада (оставляем для совместимости)
  const [questions, setQuestions] = useState([]);
  const [newQuestion, setNewQuestion] = useState("");
  const [questionsLoading, setQuestionsLoading] = useState(false);
  const [questionsError, setQuestionsError] = useState(false);

  // 🆕 Храним вопросы по каждому раскладу: { [spreadId]: Question[] }
  const [questionsBySpread, setQuestionsBySpread] = useState({});

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

  // Загрузка истории раскладов → сохраняем именно список items
  async function fetchSpreadsList(page = 1, limit = 10) {
    console.log(
      "[TMA] API GET /spreads?page=%s&limit=%s",
      page,
      limit
    );
    const res = await apiGet(`/spreads?page=${page}&limit=${limit}`);

    if (res?.ok && res.data && Array.isArray(res.data.items)) {
      setSpreads(res.data.items);
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

  // Загрузка списка вопросов для расклада (старый Q&A, пока оставляем)
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

  // Создание расклада (POST /spreads) — для вкладки «Расклады»
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

        // только для вкладки "Расклады"
        setCurrentSpread(detail);
        setActiveTab("spreads");

        // Обновляем список spreads (prepend) если он уже загружен
        setSpreads((prev) => {
          const prevItems = Array.isArray(prev) ? prev : [];

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

          return [newItem, ...prevItems];
        });

        // Подтянуть вопросы к только что созданному раскладу (и для Spreads, и для History)
        await loadQuestionsForSpread(detail.id);

        try {
          const questionsRes = await apiGet(
            `/spreads/${detail.id}/questions`
          );
          if (questionsRes?.ok && questionsRes.data) {
            setQuestionsBySpread((prev) => ({
              ...prev,
              [detail.id]: questionsRes.data,
            }));
          }
        } catch (e) {
          console.warn(
            "[TMA] Failed to prefetch questions for new spread",
            e
          );
        }

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

  // Сброс текущего расклада на вкладке «Расклады»
  function handleResetCurrentSpread() {
    setCurrentSpread(null);
    setQaState({ question: "", isAsking: false, answer: null });
    setQuestions([]);
    setNewQuestion("");
    setQuestionsError(false);
  }

  // Обновление профиля
  async function handleUpdateProfile(update) {
    console.log("[TMA] Updating profile with payload:", update);
    const res = await apiPost("/profile", update);
    console.log("[TMA] Profile updated:", res);

    if (res?.ok && res.data) {
      console.log("[TMA] New profile from API:", res.data);
      setProfile(res.data); // <-- после POST используем именно обновлённый профиль с бэка
    }
  }

  // Изменение текста нового вопроса (старый Q&A UI)
  function handleNewQuestionChange(e) {
    setNewQuestion(e.target.value);
    if (questionsError) {
      setQuestionsError("");
    }
  }

  // Выбор расклада из истории → загружаем detail + вопросы
  async function handleSelectSpreadFromHistory(id) {
    if (!id) return;
    try {
      console.log("[TMA] API GET /spreads/%s", id);
      const res = await apiGet(`/spreads/${id}`);

      if (res?.ok && res.data) {
        setHistoryDetail(res.data);
      } else {
        console.warn("[TMA] Failed to load spread detail", res);
      }

      // Подгружаем вопросы по этому раскладу
      console.log("[TMA] API GET /spreads/%s/questions", id);
      const questionsRes = await apiGet(`/spreads/${id}/questions`);
      if (questionsRes?.ok && questionsRes.data) {
        setQuestionsBySpread((prev) => ({
          ...prev,
          [id]: questionsRes.data,
        }));
      }
    } catch (e) {
      console.error("[TMA] Error in handleSelectSpreadFromHistory", e);
    }
  }

  // Новый глобальный Q&A для истории: задаём вопрос по выбранному раскладу
  async function handleAskQuestion(spreadId, text) {
    const effectiveSpreadId = spreadId ?? historyDetail?.id;
    const questionText = (text ?? "").trim();

    if (!effectiveSpreadId || !questionText) return;

    setIsAskingQuestion(true);

    try {
      console.log(
        "[TMA] API POST /spreads/%s/questions",
        effectiveSpreadId
      );
      const res = await apiPost(
        `/spreads/${effectiveSpreadId}/questions`,
        { question: questionText }
      );

      if (res?.ok && res.data) {
        // Обновляем компактное состояние Q&A (для SpreadsScreen, если нужно)
        setQaState({
          question: questionText,
          isAsking: false,
          answer: res.data,
        });

        // Обновляем список вопросов по этому раскладу
        setQuestionsBySpread((prev) => {
          const prevList = prev[effectiveSpreadId] || [];
          const nextList = Array.isArray(res.data)
            ? res.data
            : [...prevList, res.data];

          return {
            ...prev,
            [effectiveSpreadId]: nextList,
          };
        });

        console.log("[TMA] Question created for spread:", res.data);
      } else {
        console.warn("[TMA] Failed to ask question", res);
      }
    } catch (e) {
      console.error("[TMA] Error in handleAskQuestion", e);
    } finally {
      setIsAskingQuestion(false);
    }
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
            // создание/сброс расклада
            onCreateSpread={handleCreateSpread}
            onResetCurrentSpread={handleResetCurrentSpread}
            // старый Q&A-список (если ещё нужен)
            questions={questions}
            newQuestion={newQuestion}
            onNewQuestionChange={handleNewQuestionChange}
            questionsLoading={questionsLoading}
            questionsError={questionsError}
            formatDate={formatDate}
          />
        );
      case "history": {
        // Всегда стараемся отдать HistoryScreen список вопросов:
        // 1) сначала смотрим в questionsBySpread[historyDetail.id]
        // 2) если там пусто – пробуем historyDetail.questions (если бэк так хранит)
        const historyQuestions =
          historyDetail && historyDetail.id
            ? questionsBySpread[historyDetail.id] ??
              (Array.isArray(historyDetail.questions)
                ? historyDetail.questions
                : [])
            : [];

        return (
          <HistoryScreen
            spreads={spreads}
            initialLoading={initialLoading}
            formatDate={formatDate}
            selectedSpread={historyDetail}
            onSelectSpread={handleSelectSpreadFromHistory}
            onAskQuestion={handleAskQuestion}
            isAskingQuestion={isAskingQuestion}
            onCloseDetail={() => setHistoryDetail(null)}
            questions={historyQuestions}
          />
        );
      }
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
