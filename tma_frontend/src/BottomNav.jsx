import React from "react";

export default function BottomNav({ activeTab, onChange }) {
  return (
    <nav className="bottom-nav">
      <button
        className={activeTab === "home" ? "nav-btn active" : "nav-btn"}
        onClick={() => onChange("home")}
      >
        <span>🏠</span>
        <span>Главная</span>
      </button>

      <button
        className={activeTab === "spreads" ? "nav-btn active" : "nav-btn"}
        onClick={() => onChange("spreads")}
      >
        <span>🔮</span>
        <span>Расклады</span>
      </button>

      <button
        className={activeTab === "history" ? "nav-btn active" : "nav-btn"}
        onClick={() => onChange("history")}
      >
        <span>🗂</span>
        <span>История</span>
      </button>

      <button
        className={activeTab === "profile" ? "nav-btn active" : "nav-btn"}
        onClick={() => onChange("profile")}
      >
        <span>👤</span>
        <span>Профиль</span>
      </button>
    </nav>
  );
}
