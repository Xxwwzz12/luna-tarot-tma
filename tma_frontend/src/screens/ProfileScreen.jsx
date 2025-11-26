// tma_frontend/src/screens/ProfileScreen.jsx
import React, { useEffect, useState } from "react";

function ProfileScreen({
  profile,
  onUpdateProfile,
  theme,
  onThemeChange,
}) {
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    birth_date: "",
    gender: "",
  });

  useEffect(() => {
    if (!profile) return;
    setForm({
      first_name: profile.first_name || "",
      last_name: profile.last_name || "",
      birth_date: profile.birth_date || "",
      gender: profile.gender || "",
    });
  }, [profile]);

  const handleChange = (field) => (e) => {
    setForm((prev) => ({
      ...prev,
      [field]: e.target.value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (onUpdateProfile) onUpdateProfile(form);
  };

  return (
    <div className="page page-profile">
      {/* Верхняя карточка */}
      <div className="card profile-header">
        <div className="avatar-circle">
          <span>👤</span>
        </div>
        <div>
          <div className="profile-name">
            {profile?.first_name || "Без имени"}
          </div>
          {profile?.username && (
            <div className="profile-username">@{profile.username}</div>
          )}
        </div>
      </div>

      {/* Тема оформления */}
      <div className="card section">
        <p className="section-title">Тема оформления</p>
        <div className="pill-switch">
          <button
            type="button"
            className={theme === "light" ? "pill-option active" : "pill-option"}
            onClick={() => onThemeChange("light")}
          >
            Светлая
          </button>
          <button
            type="button"
            className={theme === "dark" ? "pill-option active" : "pill-option"}
            onClick={() => onThemeChange("dark")}
          >
            Тёмная
          </button>
          <button
            type="button"
            className={
              theme === "system" ? "pill-option active" : "pill-option"
            }
            onClick={() => onThemeChange("system")}
          >
            Системная
          </button>
        </div>
      </div>

      {/* Форма профиля */}
      <div className="card section">
        <p className="section-title">Профиль</p>

        <form className="profile-form" onSubmit={handleSubmit}>
          <div className="form-field">
            <label>Имя</label>
            <input
              type="text"
              value={form.first_name}
              onChange={handleChange("first_name")}
            />
          </div>

          <div className="form-field">
            <label>Фамилия</label>
            <input
              type="text"
              value={form.last_name}
              onChange={handleChange("last_name")}
            />
          </div>

          <div className="form-field">
            <label>Дата рождения</label>
            <input
              type="date"
              value={form.birth_date}
              onChange={handleChange("birth_date")}
            />
          </div>

          <div className="form-field">
            <label>Пол</label>
            <select
              value={form.gender}
              onChange={handleChange("gender")}
            >
              <option value="">Не указан</option>
              <option value="male">Мужской</option>
              <option value="female">Женский</option>
              <option value="other">Другое</option>
            </select>
          </div>

          <button type="submit" className="btn primary full">
            Сохранить
          </button>
        </form>
      </div>
    </div>
  );
}

export default ProfileScreen;
