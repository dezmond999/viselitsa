import asyncio
import random
import sqlite3
import hashlib
import duel
from duel import cancel_duel_search
from duel import handle_duel_input

from datetime import date

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

# ================== НАСТРОЙКИ ==================
TOKEN = "8460606222:AAHr7WMYE8souR3Fr7_QWhuHQ8TuPOB-HZI"
MAX_ERRORS = 6
with open("russian.txt", encoding="utf-8") as f:
    WORDS = [w.strip().lower() for w in f if w.strip().isalpha()]
    HARD_WORDS = [w for w in WORDS if len(w) >= 9]

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
duel.register_duel_handlers(dp, bot, WORDS)
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
    letters_total INTEGER DEFAULT 0,
    last_daily TEXT,
    nickname TEXT,
    bio TEXT
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
cursor.execute("""
CREATE TABLE IF NOT EXISTS achievements (
    user_id INTEGER,
    code TEXT,
    date TEXT,
    UNIQUE(user_id, code)
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

    cursor.execute("""
        UPDATE users
        SET letters_total = COALESCE(letters_total, 0) + ?
        WHERE user_id = ?
    """, (guessed_letters, user_id))

    db.commit()

ACHIEVEMENT_CHAINS = {

    "letters_total": [
        (10,  "letters_10",   "📚 Буквоед I"),
        (25,  "letters_25",   "📗 Буквоед II"),
        (50,  "letters_50",   "📘 Буквоед III"),
        (100, "letters_100",  "🅰️ Алфавит"),
        (500, "letters_250",  "🧠 Лингвист"),
        (1000, "letters_500",  "🧠 Полиглот"),
        (5000,"letters_1000", "🧬 Гений языка"),
    ],

    "wins": [
        (1,   "win_1",   "🥉 Первая кровь"),
        (5,   "win_5",   "🥉 Вошёл во вкус"),
        (20,  "win_10",  "🥈 Ветеран"),
        (50,  "win_25",  "🥈 Мастер слов"),
        (100,  "win_50",  "🥇 Легенда"),
        (500, "win_100", "🏆 Абсолют"),
    ],

    "streak": [
        (3,  "streak_3",  "🔥 Разогрев"),
        (5,  "streak_5",  "🔥 Серия I"),
        (7,  "streak_7",  "🔥 Серия II"),
        (10, "streak_10", "🔥 Неостановим"),
    ],
}
ACHIEVEMENTS_INFO = {
    # letters_total
    "letters_10":   "Угадай 10 букв суммарно",
    "letters_25":   "Угадай 25 букв суммарно",
    "letters_50":   "Угадай 50 букв суммарно",
    "letters_100":  "Угадай 100 букв суммарно",
    "letters_250":  "Угадай 500 букв суммарно",
    "letters_500":  "Угадай 1000 букв суммарно",
    "letters_1000": "Угадай 5000 букв суммарно",

    # wins
    "win_1":   "Выиграй 1 игру",
    "win_5":   "Выиграй 5 игр",
    "win_10":  "Выиграй 20 игр",
    "win_25":  "Выиграй 50 игр",
    "win_50":  "Выиграй 100 игр",
    "win_100": "Выиграй 500 игр",

    # streak
    "streak_3":  "Выиграй 3 игры подряд",
    "streak_5":  "Выиграй 5 игр подряд",
    "streak_7":  "Выиграй 7 игр подряд",
    "streak_10": "Выиграй 10 игр подряд"
}
def has_achievement(user_id, code):
    cursor.execute(
        "SELECT 1 FROM achievements WHERE user_id=? AND code=?",
        (user_id, code)
    )
    return cursor.fetchone() is not None


def give_achievement(user_id, code):
    if has_achievement(user_id, code):
        return False

    cursor.execute(
        "INSERT INTO achievements (user_id, code, date) VALUES (?, ?, ?)",
        (user_id, code, date.today().isoformat())
    )
    db.commit()
    return True
def process_chain(user_id, chain, value, new_achievements):
    for threshold, code, title in chain:
        if value >= threshold:
            if give_achievement(user_id, code):
                new_achievements.append(title)
def get_chain_progress(chain, value):
    for threshold, _, _ in chain:
        if value < threshold:
            return value, threshold
    return value, value  # цепочка закрыта


# ================== КОМАНДЫ ==================
@dp.message(F.text == "/start")
async def start(message: Message):
    ensure_profile(
        message.from_user.id,
        message.from_user.full_name
    )
    await message.answer(
        "🎮 Виселица\n\n"
        "/profile — профиль\n"
        "/new — новая игра\n"
        "/hard — сложный режим(х1.5)\n\n"
        "/daily — ежедневное слово\n"
        "/stats — статистика\n"
        "/achievements — достижения\n\n"
        "/duel — случайная дуэль\n"
        "/duel @username — вызов на дуэль\n\n"
        
        "Пиши по одной букве или сразу целое слово!\n\n"
        "/top — рейтинг за всё время\n"
        "/week_top — рейтинг за неделю\n"
        "/month_top — рейтинг за месяц\n"
    )

@dp.message(F.text == "/profile")
async def profile(message: Message):
    user = get_user(message.from_user.id)

    nickname = user[8] or message.from_user.full_name
    bio = user[9] or "—"

    text = (
        "👤 Профиль игрока\n\n"
        f"🏷 Ник: {nickname}\n"
        f"📝 О себе:\n{bio}\n\n"
        "🎮 Одиночная игра:\n"
        f"🏆 Побед: {user[2]}\n"
        f"📚 Букв: {user[6]}\n\n"
        "⚔️ Дуэли:\n— скоро —\n\n"
        "✏️ /set_nick [ник] — изменить ник\n"
        "✏️ /set_bio [текст] — изменить описание"
    )

    await message.answer(text)
@dp.message(F.text.startswith("/set_nick "))
async def set_nick(message: Message):
    nick = message.text.replace("/set_nick", "").strip()

    if len(nick) < 3 or len(nick) > 20:
        await message.answer("❌ Ник должен быть от 3 до 20 символов")
        return

    cursor.execute(
        "UPDATE users SET nickname=? WHERE user_id=?",
        (nick, message.from_user.id)
    )
    db.commit()

    await message.answer(f"✅ Ник изменён на: {nick}")
@dp.message(F.text.startswith("/set_bio "))
async def set_bio(message: Message):
    bio = message.text.replace("/set_bio", "").strip()

    if len(bio) > 120:
        await message.answer("❌ Описание слишком длинное (макс 120 символов)")
        return

    cursor.execute(
        "UPDATE users SET bio=? WHERE user_id=?",
        (bio, message.from_user.id)
    )
    db.commit()

    await message.answer("✅ Описание обновлено")

@dp.message(F.text == ("/achievements"))
async def achievements(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)

    values = {
        "letters_total": user[6],
        "wins": user[2],
        "streak": user[4],
    }

    text = "🏆 Достижения:\n\n"

    for chain_name, chain in ACHIEVEMENT_CHAINS.items():
        text += f"🔹 {chain_name.replace('_', ' ').title()}\n"

        value = values[chain_name]

        for threshold, code, title in chain:
            description = ACHIEVEMENTS_INFO.get(code, "")

            if has_achievement(user_id, code):
                text += f"✅ {title}\n   └ {description}\n"
            else:
                if value >= threshold:
                    text += f"🟡 {title} — готово!\n   └ {description}\n"
                else:
                    text += f"🔒 {title} ({value}/{threshold})\n   └ {description}\n"
        text += "\n"

    await message.answer(text)


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
def ensure_profile(user_id, tg_name):
    cursor.execute(
        "SELECT nickname FROM users WHERE user_id=?",
        (user_id,)
    )
    row = cursor.fetchone()

    if row is None:
        cursor.execute(
            "INSERT INTO users (user_id, nickname) VALUES (?, ?)",
            (user_id, tg_name)
        )
    elif row[0] is None:
        cursor.execute(
            "UPDATE users SET nickname=? WHERE user_id=?",
            (tg_name, user_id)
        )
    db.commit()

@dp.message(F.text == "/new")
async def new_game(message: Message):
    word = random.choice(WORDS)

    games[message.from_user.id] = {
        "word": word,
        "guessed": set(),
        "wrong": set(),
        "errors": 0,
        "daily": False,
        "mode": "normal",
        "max_errors": MAX_ERRORS,
        "guessed_letters": 0
    }

    await message.answer(
        "🔤 Я загадал слово:\n"
        f"{masked_word(word, set())}"
    )

@dp.message(F.text == "/hard")
async def hard_game(message: Message):
    if not HARD_WORDS:
        await message.answer("❌ Нет слов для сложного режима")
        return

    word = random.choice(HARD_WORDS)

    games[message.from_user.id] = {
        "word": word,
        "guessed": set(),
        "wrong": set(),
        "errors": 0,
        "daily": False,
        "mode": "hard",
        "max_errors": 5,
        "guessed_letters": 0
    }

    await message.answer(
        "🔥 СЛОЖНЫЙ РЕЖИМ\n"
        "Слова от 9 букв\n"
        "Ошибок меньше, награды больше\n\n"
        f"{masked_word(word, set())}"
    )

@dp.message(F.text == "/daily")
async def daily(message: Message):
    user_id = message.from_user.id
    today = date.today().isoformat()

    user = get_user(user_id)
    if user[7] == today:
        await message.answer("⏳ Ты уже играл сегодня")
        return

    word = get_daily_word()

    games[user_id] = {
        "word": word,
        "guessed": set(),
        "wrong": set(),
        "errors": 0,
        "daily": True,
        "mode": "normal",
        "max_errors": MAX_ERRORS,
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

    current_letters = 0
    if message.from_user.id in games:
        current_letters = games[message.from_user.id]["guessed_letters"]

    await message.answer(
        "📊 Твоя статистика:\n"
        f"🎮 Игр: {user[1]}\n"
        f"🏆 Побед: {user[2]}\n"
        f"💀 Поражений: {user[3]}\n"
        f"🔥 Стрик: {user[4]}\n"
        f"⭐ Лучший стрик: {user[5]}\n\n"
        f"🔤 Букв сейчас: {current_letters}\n"
        f"📚 Букв всего: {user[6] or 0}"
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
        unique_letters = set(word)
        game["guessed_letters"] += len(unique_letters)
        update_stats(user_id, True)
        log_game(user_id, 1, game["errors"], game["guessed_letters"])
        user = get_user(user_id) 
        new_achievements = []

        user = get_user(user_id)
        
        process_chain(
            user_id,
            ACHIEVEMENT_CHAINS["letters_total"],
            user[6],  # letters_total
            new_achievements
        )

        process_chain(
            user_id,
            ACHIEVEMENT_CHAINS["wins"],
            user[2],
            new_achievements
        )

        process_chain(
            user_id,
            ACHIEVEMENT_CHAINS["streak"],
            user[4],
            new_achievements
        )
        if game["daily"]:
            cursor.execute(
                "UPDATE users SET last_daily=? WHERE user_id=?",
                (date.today().isoformat(), user_id)
            )
            db.commit()

        del games[user_id]
        text = f"🎉 Победа!\nСлово: {game['word']}\n"
        if new_achievements:
            text += "\n🏅 Новые достижения:\n"
            for a in new_achievements:
                text += f"• {a}\n"

        text += "\nНапиши /new или /hard для новой игры или /start для выхода в меню"

        await message.answer(text)
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
            f"Напиши /new или /hard для новой игры или /start для выхода в главное меню"
        )
def render_game(game):
    word_view = masked_word(game["word"], game["guessed"])
    wrong_letters = ", ".join(sorted(game["wrong"])) or "—"

    return (
        f"{HANGMAN[game['errors']]}\n"
        f"{word_view}\n\n"
        f"❌ Ошибочные буквы:\n"
        f"{wrong_letters}\n\n"
        f"💥 Ошибок: {game['errors']} / {game['max_errors']}"
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
        user = get_user(user_id) 
        new_achievements = []

        user = get_user(user_id)

        user = get_user(user_id)

        process_chain(
            user_id,
            ACHIEVEMENT_CHAINS["letters_total"],
            user[6],  # letters_total
            new_achievements
        )

        process_chain(
            user_id,
            ACHIEVEMENT_CHAINS["wins"],
            user[2],
            new_achievements
        )

        process_chain(
            user_id,
            ACHIEVEMENT_CHAINS["streak"],
            user[4],
            new_achievements
        )
        if game["daily"]:
            cursor.execute(
                "UPDATE users SET last_daily=? WHERE user_id=?",
                (date.today().isoformat(), user_id)
            )
            db.commit()

        del games[user_id]
        text = f"🎉 Победа!\nСлово: {game['word']}\n"

        if new_achievements:
            text += "\n🏅 Новые достижения:\n"
            for a in new_achievements:
                text += f"• {a}\n"

        text += "\nНапиши /new или /hard для новой игры или /start для выхода в меню"

        await message.answer(text)
        return

    # ПОРАЖЕНИЕ
    if game["errors"] >= game["max_errors"]:
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
            f"Напиши /new или /hard для новой игры или /start для выхода в главное меню"
        )
        return

    await message.answer(render_game(game))

@dp.message(F.text.startswith("/"), F.text != "/duel")
async def command_intercept(message: Message):
    user_id = message.from_user.id

    if cancel_duel_search(user_id):
        await message.answer("❌ Поиск дуэли отменён")


@dp.message(F.text & ~F.text.startswith("/"))
async def duel_intercept(message: Message):
    handled = await handle_duel_input(bot, message)
    if handled:
        return
# ================== ЗАПУСК ==================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
