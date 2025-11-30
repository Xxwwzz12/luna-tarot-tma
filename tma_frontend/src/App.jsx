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

  // Профиль пользователя
  const [profile, setProfile] = useState(null);

  // История раскладов (список)
  const [spreads, setSpreads] = useState({ items: [] });

  // Текущий расклад (detail или элемент из списка)
  // Важно: currentSpread намеренно НЕ сбрасывается при смене вкладок —
  // чтобы можно было вернуться к уже открытому раскладу.
  // currentSpread.cards — это «истинные» карты расклада, пришедшие с бэка (для viewer-карусели).
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

  // Лог initData один раз (чисто диагностический)
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

        console.log("[TMA] API_BASE_URL:", import.meta.env.VITE_API_BASE_URL);

        const [profileData, spreadsData] = await Promise.all([
          fetchProfile(),
          fetchSpreads(),
        ]);

        console.log("[TMA] Profile loaded:", {
          user_id: profileData?.user_id,
          username: profileData?.username,
        });

        setProfile(profileData);

        if (spreadsData && Array.isArray(spreadsData.items)) {
          console.log(
            "[TMA] Spreads list loaded:",
            spreadsData.items.length,
            "items"
          );
          setSpreads({
            items: spreadsData.items,
            total_items: spreadsData.total_items,
          });
        } else {
          console.log("[TMA] Spreads list is empty or invalid.");
        }
      } catch (e) {
        console.error("[TMA] Initial load error:", e);
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

      // не добавляем дубликаты по id+position (или только id, если position нет)
      const isDuplicate = prev.some(
        (c) =>
          c &&
          card &&
          c.id === card.id &&
          // position может быть undefined, поэтому сравниваем тоже аккуратно
          (c.position === card.position || c.position === undefined)
      );
      if (isDuplicate) return prev;

      let next = [...prev, card];

      // ограничиваем по количеству карт
      if (next.length > maxCards) {
        next = next.slice(0, maxCards);
      }

      return next;
    });
  }

  // Создание расклада (handleCreateSpread)
  // СИНХРОНИЗАЦИЯ КОНТРАКТА:
  // - Если SpreadsScreen вызывает onCreateSpread(payloadFromChild),
  //   используем этот payload.
  // - Если вызывается без аргумента, собираем payload из стейта App (старое поведение).
  // selectedCards при этом НЕ уходят на сервер — это только фронтовый ритуал.
  async function handleCreateSpread(payloadFromChild) {
    try {
      setLoading(true);
      setError(null);

      const basePayload = {
        spread_type: spreadType,
        category,
        mode: "auto",
        question: question.trim() || null,
      };

      const payload = payloadFromChild ?? basePayload;

      const detail = await createAutoSpread(payload);

      const detailWithQuestion = {
        ...detail,
        question: payload.question || null,
      };

      // Сохраняем детальный расклад и переходим на вкладку "Расклады"
      setCurrentSpread(detailWithQuestion);
      setActiveTab("spreads");

      // Обновляем историю
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

        const prevItems = prev.items || [];
        const prevTotal =
          typeof prev.total_items === "number"
            ? prev.total_items
            : prevItems.length;

        return {
          ...prev,
          items: [newItem, ...prevItems],
          total_items: prevTotal + 1,
        };
      });

      // подгружаем вопросы уже по созданному раскладу
      await loadQuestionsForSpread(detail.id);

      // сброс вопроса и выбранных карт после успешного создания
      setQuestion("");
      setSelectedCards([]); // picker очищается после ритуала
      setNewQuestion("");
    } catch (err) {
      console.error("Create spread error:", err);
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
      console.error("Update profile error:", err);
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

    // found — это элемент списка (list item), не обязательно полный detail,
    // но его достаточно, чтобы показать краткий просмотр.
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
