import asyncio
import random
import sqlite3
import hashlib
from datetime import date

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

# ================== НАСТРОЙКИ ==================
TOKEN = "8460606222:AAHr7WMYE8souR3Fr7_QWhuHQ8TuPOB-HZI"
MAX_ERRORS = 6
with open("russian.txt", encoding="utf-8") as f:
    WORDS = [w.strip().lower() for w in f if w.strip().isalpha()]
HANGMAN = [
    "",
    "😐",
    "😐\n |",
    "😐\n/|",
    "😐\n/|\\",
    "😐\n/|\\\n/",
    "😵\n/|\\\n/ \\",
]

# ================== БОТ ==================
bot = Bot(token=TOKEN)
dp = Dispatcher()

games = {}  # user_id -> game_state

# ================== БАЗА ДАННЫХ ==================
db = sqlite3.connect("stats.db")
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    games INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    loses INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    last_daily TEXT
)
""")
db.commit()
cursor.execute("""
CREATE TABLE IF NOT EXISTS games_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    date TEXT,
    win INTEGER,
    errors INTEGER,
    guessed_letters INTEGER
)
""")
db.commit()


def get_user(user_id: int):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        db.commit()
        return get_user(user_id)
    return user


def update_stats(user_id: int, win: bool):
    get_user(user_id)

    if win:
        cursor.execute("""
        UPDATE users
        SET games = games + 1,
            wins = wins + 1,
            streak = streak + 1,
            best_streak = MAX(best_streak, streak + 1)
        WHERE user_id = ?
        """, (user_id,))
    else:
        cursor.execute("""
        UPDATE users
        SET games = games + 1,
            loses = loses + 1,
            streak = 0
        WHERE user_id = ?
        """, (user_id,))
    db.commit()


# ================== ЛОГИКА ==================
def get_top(limit=10):
    cursor.execute("""
        SELECT user_id, wins, best_streak
        FROM users
        ORDER BY wins DESC, best_streak DESC
        LIMIT ?
    """, (limit,))
    return cursor.fetchall()

def masked_word(word, guessed):
    return " ".join(c if c in guessed else "_" for c in word)


def get_daily_word():
    today = date.today().isoformat()
    seed = int(hashlib.md5(today.encode()).hexdigest(), 16)
    return WORDS[seed % len(WORDS)]

def log_game(user_id, win, errors, guessed_letters):
    today = date.today().isoformat()
    cursor.execute("""
        INSERT INTO games_log (user_id, date, win, errors, guessed_letters)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, today, win, errors, guessed_letters))
    db.commit()

# ================== КОМАНДЫ ==================
@dp.message(F.text == "/week_top")
async def week_top(message: Message):
    cursor.execute("""
        SELECT user_id,
               SUM(CASE WHEN win = 1 THEN 1 ELSE 0 END) AS wins,
               COUNT(*) AS games,
               SUM(errors) AS errors,
               SUM(guessed_letters) AS guessed_letters
        FROM games_log
        WHERE date >= date('now', '-6 days')
        GROUP BY user_id
        ORDER BY wins DESC, errors ASC
        LIMIT 10
    """)

    rows = cursor.fetchall()
    if not rows:
        await message.answer("За неделю ещё никто не играл 😴")
        return

    text = "🏆 ТОП ЗА НЕДЕЛЮ\n\n"

    for i, (user_id, wins, games, errors, guessed_letters) in enumerate(rows, 1):
        try:
            user = await bot.get_chat(user_id)
            name = user.full_name
        except:
            name = "anon"

        text += (
            f"{i}️⃣ {name}\n"
            f"🏆 Побед: {wins} | 🎮 Игр: {games}\n"
            f"❌ Ошибок: {errors}\n"
            f"🔤 Букв: {guessed_letters}\n"
        )

    await message.answer(text)

@dp.message(F.text == "/month_top")
async def month_top(message: Message):
    cursor.execute("""
        SELECT user_id,
               SUM(CASE WHEN win = 1 THEN 1 ELSE 0 END) AS wins,
               COUNT(*) AS games,
               SUM(errors) AS errors,
               SUM(guessed_letters) AS guessed_letters
        FROM games_log
        WHERE date >= date('now', 'start of month')
        GROUP BY user_id
        ORDER BY wins DESC, errors ASC
        LIMIT 10
    """)

    rows = cursor.fetchall()
    if not rows:
        await message.answer("В этом месяце ещё никто не играл 😴")
        return

    text = "🏅 ТОП ЗА МЕСЯЦ\n\n"

    for i, (user_id, wins, games, errors, guessed_letters) in enumerate(rows, 1):
        try:
            user = await bot.get_chat(user_id)
            name = user.full_name
        except:
            name = "anon"

        text += (
            f"{i}️⃣ {name}\n"
            f"🏆 Побед: {wins} | 🎮 Игр: {games}\n"
            f"❌ Ошибок: {errors}\n"
            f"🔤 Букв: {guessed_letters}\n"
        )

    await message.answer(text)


@dp.message(F.text == "/top")
async def top(message: Message):
    top_users = get_top()

    if not top_users:
        await message.answer("Рейтинг пока пуст 😢")
        return

    text = "🏆 ТОП-10 ИГРОКОВ\n\n"

    for i, (user_id, wins, best_streak) in enumerate(top_users, start=1):
        try:
            user = await bot.get_chat(user_id)
            name = f"@{user.username}" if user.username else user.full_name
        except:
            name = "anon"

        text += (
            f"{i}️⃣ {name} — "
            f"🏆 {wins} | 🔥 {best_streak}\n"
        )

    await message.answer(text)

@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer(
        "🎮 Виселица\n\n"
        "/new — новая игра\n"
        "/daily — ежедневное слово\n"
        "/stats — статистика\n\n"
        "Пиши по ОДНОЙ букве\n\n"
        "/top — рейтинг\n"
    )


@dp.message(F.text == "/new")
async def new_game(message: Message):
    word = random.choice(WORDS)

    games[message.from_user.id] = {
        "word": word,
        "guessed": set(),
        "wrong": set(),
        "errors": 0,
        "daily": False,
        "guessed_letters": 0
    }

    await message.answer(
        "🔤 Я загадал слово:\n"
        f"{masked_word(word, set())}"
    )


@dp.message(F.text == "/daily")
async def daily(message: Message):
    user_id = message.from_user.id
    today = date.today().isoformat()

    user = get_user(user_id)
    if user[6] == today:
        await message.answer("⏳ Ты уже играл сегодня")
        return

    word = get_daily_word()

    games[user_id] = {
        "word": word,
        "guessed": set(),
        "wrong": set(),
        "errors": 0,
        "daily": True,
        "guessed_letters": 0
    }

    await message.answer(
        "🗓 ЕЖЕДНЕВНОЕ СЛОВО\n"
        "Одна попытка в день!\n\n"
        f"{masked_word(word, set())}"
    )


@dp.message(F.text == "/stats")
async def stats(message: Message):
    user = get_user(message.from_user.id)

    await message.answer(
        "📊 Твоя статистика:\n"
        f"🎮 Игр: {user[1]}\n"
        f"🏆 Побед: {user[2]}\n"
        f"💀 Поражений: {user[3]}\n"
        f"🔥 Стрик: {user[4]}\n"
        f"⭐ Лучший стрик: {user[5]}"
    )

@dp.message(F.text.len() > 1)
async def guess_word(message: Message):
    user_id = message.from_user.id
    text = message.text.lower()

    if text.startswith("/"):
        return

    if user_id not in games:
        await message.answer("Напиши /new или /daily")
        return

    game = games[user_id]
    word = game["word"]
    

    # ❌ неправильная длина
    if len(text) != len(word):
        await message.answer(
            "❗ Неправильный ввод\n"
            "Введите ОДНУ букву или слово целиком"
        )
        return

    # ✅ попытка угадать слово
    if text == word:
        update_stats(user_id, True)
        log_game(user_id, 1, game["errors"], game["guessed_letters"])

        if game["daily"]:
            cursor.execute(
                "UPDATE users SET last_daily=? WHERE user_id=?",
                (date.today().isoformat(), user_id)
            )
            db.commit()

        del games[user_id]
        await message.answer(f"🎉 Победа!\nСлово: {game['word']}\nНапиши /new для новой игры или /start для выхода в главное меню")
    else:
        update_stats(user_id, False)
        log_game(user_id, 0, game["errors"], game["guessed_letters"])

        if game["daily"]:
            cursor.execute(
                "UPDATE users SET last_daily=? WHERE user_id=?",
                (date.today().isoformat(), user_id)
            )
            db.commit()

        del games[user_id]
        await message.answer(
            "💀 Неверно!\n"
            f"Ты проиграл.\n"
            f"Слово было: {word}\n"
            f"Напиши /new для новой игры или /start для выхода в главное меню"
        )
def render_game(game):
    word_view = masked_word(game["word"], game["guessed"])
    wrong_letters = ", ".join(sorted(game["wrong"])) or "—"

    return (
        f"{HANGMAN[game['errors']]}\n"
        f"{word_view}\n\n"
        f"❌ Ошибочные буквы:\n"
        f"{wrong_letters}\n\n"
        f"💥 Ошибок: {game['errors']} / {MAX_ERRORS}"
    )
# ================== ВВОД БУКВ ==================
@dp.message(F.text.len() == 1)
async def letter(message: Message):
    user_id = message.from_user.id

    if user_id not in games:
        await message.answer("Напиши /new или /daily")
        return

    game = games[user_id]
    letter = message.text.lower()

    if not letter.isalpha():
        return

    if letter in game["guessed"]:
        await message.answer("⚠️ Уже было")
        return

    game["guessed"].add(letter)

    if letter in game["word"]:
        # ✅ считаем угаданные буквы
        game["guessed_letters"] += game["word"].count(letter)
    else:
        game["errors"] += 1
        game["wrong"].add(letter)


    word_view = masked_word(game["word"], game["guessed"])

    # ПОБЕДА
    if "_" not in word_view:
        update_stats(user_id, True)
        log_game(user_id, 1, game["errors"], game["guessed_letters"])

        if game["daily"]:
            cursor.execute(
                "UPDATE users SET last_daily=? WHERE user_id=?",
                (date.today().isoformat(), user_id)
            )
            db.commit()

        del games[user_id]
        await message.answer(f"🎉 Победа!\nСлово: {game['word']}\nНапиши /new для новой игры или /start для выхода в главное меню")
        return

    # ПОРАЖЕНИЕ
    if game["errors"] >= MAX_ERRORS:
        update_stats(user_id, False)
        log_game(user_id, 0, game["errors"], game["guessed_letters"])

        if game["daily"]:
            cursor.execute(
                "UPDATE users SET last_daily=? WHERE user_id=?",
                (date.today().isoformat(), user_id)
            )
            db.commit()

        del games[user_id]
        await message.answer(
            f"{HANGMAN[MAX_ERRORS]}\n"
            f"💀 Ты проиграл\n"
            f"Слово было: {game['word']}\n"
            f"Напиши /new для новой игры или /start для выхода в главное меню"
        )
        return

    await message.answer(render_game(game))


# ================== ЗАПУСК ==================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
