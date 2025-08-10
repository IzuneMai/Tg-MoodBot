import os
import sqlite3
from datetime import datetime, timedelta
from io import BytesIO
import math

import matplotlib.pyplot as plt
import telebot

bot = telebot.TeleBot('8495023692:AAGYNbqOVCWnizEmU2h3onC0elJxSRTIrAI')

#База данных

DB_PATH = "moods.db"
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS moods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            dt TEXT NOT NULL,           -- ISO8601
            emoji TEXT NOT NULL,
            comment TEXT
        )
    """)
    conn.commit()
    return conn

# Оценка настроения по эмодзи
scores = {
    "😢": 1, "😡": 1,
    "😕": 2, "😴": 2,
    "😐": 3,
    "🙂": 4,
    "😀": 5, "😌": 5,
}
supported = list(scores.keys())

def now():
    return datetime.now()

def save_mood(chat_id: int, emoji: str, comment: str | None):
    conn = get_db()
    conn.execute(
        "INSERT INTO moods(chat_id, dt, emoji, comment) VALUES (?, ?, ?, ?)",
        (chat_id, now().isoformat(timespec="seconds"), emoji, comment)
    )
    conn.commit()
    conn.close()

def get_today_last(chat_id: int):
    start = now().replace(hour=0, minute=0, second=0)
    end = start + timedelta(days=1)
    conn = get_db()
    cur = conn.execute(
        "SELECT emoji, comment, dt FROM moods WHERE chat_id=? AND dt BETWEEN ? AND ? ORDER BY dt DESC LIMIT 1",
        (chat_id, start.isoformat(), end.isoformat())
    )
    row = cur.fetchone()
    conn.close()
    return row  # (emoji, comment, dt) или None

def get_daily_scores(chat_id: int, days: int = 7):
    # Возвращает списки дат (str) и средних баллов (float|nan) за каждый день
    labels, values = [], []
    conn = get_db()
    for i in range(days-1, -1, -1):
        day = (now() - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day + timedelta(days=1)
        cur = conn.execute(
            "SELECT emoji FROM moods WHERE chat_id=? AND dt BETWEEN ? AND ?",
            (chat_id, day.isoformat(), day_end.isoformat())
        )
        emojis = [r[0] for r in cur.fetchall()]
        scores = [scores[e] for e in emojis if e in scores]
        avg = sum(scores)/len(scores) if scores else math.nan
        labels.append(day.strftime("%d.%m"))
        values.append(avg)
    conn.close()
    return labels, values

def plot_chart(labels, values):
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(labels, values, marker="o", color="#5b8def", linewidth=2)
    ax.set_ylim(0.5, 5.5)
    ax.set_yticks([1,2,3,4,5])
    ax.set_ylabel("настроение")
    ax.set_title("Твоя неделя настроения")
    ax.grid(True, linestyle="--", alpha=0.4)
    # Подсветка «сегодня»
    ax.scatter([labels[-1]], [values[-1]], color="#e85d75", zorder=3)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=200)
    plt.close(fig)
    buf.seek(0)
    bot.send_document(buf)
    return buf
    

#Команды
HELP_TEXT = (
    "Я помогу отслеживать настроение.\n\n"
    "Команды:\n"
    "• /start\n"
    "• /help\n"
    "• /mood [эмодзи] [комментарий]\n"
    "  пример: /мood 🙂 спокойный день\n"
    "• /today — показать запись за сегодня\n"
    "• /diagram — неделя настроения (PNG)\n\n"
    f"Поддерживаемые эмодзи: {' '.join(supported)}"
)

@bot.message_handler(commands = ['start'])
def main(message):
    bot.send_message(message.chat.id, f'Здарова, {message.from_user.first_name}, епта')

@bot.message_handler(commands = ['help'])
def main(message):
    bot.send_message(message.chat.id, HELP_TEXT)

@bot.message_handler(commands=["mood", "настроение"])
def mood_cmd(message):
    # Ожидаем: /mood 🙂 опциональный текст...
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        return bot.reply_to(message, "Добавь эмодзи: например, /mood 🙂 спокойный день")
    emoji = parts[1]
    comment = parts[2] if len(parts) >= 3 else None

    if emoji not in supported:
        return bot.reply_to(
            message,
            f"Пока я понимаю только эти эмодзи: {' '.join(supported)}\n"
            "Пример: /mood 🙂 прогулка удалась"
        )

    save_mood(message.chat.id, emoji, comment)
    suffix = f" — {comment}" if comment else ""
    bot.reply_to(message, f"Сохранил настроение: {emoji}{suffix}")

@bot.message_handler()
def mess(message):
    if message.text.lower() == "/today":
        row = get_today_last(message.chat.id)
        if not row:
            return bot.reply_to(message, "Сегодня ещё нет записи. Напиши: /mood 🙂 короткий комментарий")
        emoji, comment, dt = row
        t = datetime.fromisoformat(dt).strftime("%H:%M")
        suffix = f" — {comment}" if comment else ""
        bot.reply_to(message, f"Сегодня в {t}: {emoji}{suffix}")
    elif message.text.lower() == '/diagram':
        labels, values = get_daily_scores(message.chat.id, days=7)
        buf = plot_chart(labels, values)
        bot.send_photo(message.chat.id, buf, caption="Неделя настроения (1 — грустно, 5 — отлично)")


# Фолбэк: если пользователь просто прислал эмодзи из набора
@bot.message_handler(func=lambda m: m.text and m.text.strip() in supported)
def quick_mood(message):
    emoji = message.text.strip()
    save_mood(message.chat.id, emoji, None)
    bot.reply_to(message, f"Сохранил настроение: {emoji}")

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling(skip_pending=True, allowed_updates=["message"])