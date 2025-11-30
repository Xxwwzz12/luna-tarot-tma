// tma_frontend/src/screens/ProfileScreen.jsx
import React, { useEffect, useState } from "react";

function ProfileScreen({ profile, onUpdateProfile, theme, onThemeChange }) {
  // Стейты по ТЗ P2
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [gender, setGender] = useState("");

  // Инициализация из profile
  useEffect(() => {
    if (!profile) return;
    setFirstName(profile.first_name || "");
    setLastName(profile.last_name || "");
    setBirthDate(profile.birth_date || "");
    setGender(profile.gender || "");
  }, [profile]);

  const handleSubmit = (e) => {
    e.preventDefault();

    // Важно: только нормализованный payload, без fetch внутри
    onUpdateProfile?.({
      first_name: firstName || null,
      last_name: lastName || null,
      birth_date: birthDate || null,
      gender: gender || null,
    });
  };

  return (
    <div className="page page-profile">
      {/* Верхняя карточка с аватаром */}
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

      {/* Блок выбора темы */}
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
            <label htmlFor="first_name">Имя</label>
            <input
              id="first_name"
              type="text"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              placeholder="Ваше имя"
            />
          </div>

          <div className="form-field">
            <label htmlFor="last_name">Фамилия</label>
            <input
              id="last_name"
              type="text"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              placeholder="Ваша фамилия"
            />
          </div>

          <div className="form-field">
            <label htmlFor="birth_date">Дата рождения</label>
            <input
              id="birth_date"
              type="date"
              value={birthDate || ""}
              onChange={(e) => setBirthDate(e.target.value)}
            />
          </div>

          <div className="form-field">
            <label htmlFor="gender">Пол</label>
            <select
              id="gender"
              value={gender || ""}
              onChange={(e) => setGender(e.target.value)}
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
