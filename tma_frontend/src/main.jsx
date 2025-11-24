import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./index.css";

// Инициализация window.__tma
if (typeof window !== "undefined") {
  const tg = window.Telegram?.WebApp;
  window.__tma = {
    initData: tg?.initData || null,
  };
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <App />
);
