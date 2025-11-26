// tma_frontend/src/screens/HomeScreen.jsx
import React from "react";

function HomeScreen({ onGoSpreads, onGoHistory, onGoProfile }) {
  return (
    <div className="page page-home">
      {/* Приветственный блок */}
      <section className="hero-card card">
        <p className="hero-label">Luna Tarot</p>
        <h1>Что хотите узнать сегодня?</h1>
        <p className="hero-sub">
          Выберите расклад, посмотрите историю или обновите профиль.
        </p>
      </section>

      {/* Основные плитки */}
      <section className="home-grid">
        {/* Расклады */}
        <button className="home-tile card" onClick={onGoSpreads}>
          <div className="home-icon">🔮</div>
          <div className="home-title">Расклады Таро</div>
          <div className="home-sub">Карта дня и 3 карты</div>
        </button>

        {/* Натальная карта — заглушка */}
        <button className="home-tile card disabled" disabled>
          <div className="home-icon">☀</div>
          <div className="home-title">Натальная карта</div>
          <div className="home-sub">Скоро появится</div>
        </button>

        {/* История */}
        <button className="home-tile card" onClick={onGoHistory}>
          <div className="home-icon">🗂</div>
          <div className="home-title">История</div>
          <div className="home-sub">Ваши прошлые расклады</div>
        </button>

        {/* Профиль */}
        <button className="home-tile card" onClick={onGoProfile}>
          <div className="home-icon">👤</div>
          <div className="home-title">Профиль</div>
          <div className="home-sub">Данные и настройки</div>
        </button>
      </section>
    </div>
  );
}

export default HomeScreen;
