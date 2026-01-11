# duel.py
import time
import random
import uuid

from aiogram import F
from aiogram.types import Message

# ==================================================
# СОСТОЯНИЯ ДУЭЛЕЙ
# ==================================================

duel_queue = []      # очередь поиска (user_id)
duels = {}           # duel_id -> duel_state
user_to_duel = {}    # user_id -> duel_id


# ==================================================
# УТИЛИТЫ
# ==================================================

def generate_word(words):
    return random.choice(words)


def masked_word(word, guessed):
    return " ".join(c if c in guessed else "_" for c in word)


# ==================================================
# СОЗДАНИЕ ДУЭЛИ
# ==================================================

def create_duel(player1, player2, words):
    duel_id = str(uuid.uuid4())

    word = generate_word(words)

    duels[duel_id] = {
        "players": [player1, player2],
        "score": {
            player1: 0,
            player2: 0
        },
        "round": 1,
        "max_rounds": 5,
        "extra": False,

        "word": word,
        "round_active": True,
        "winner_round": None,

        "games": {
            player1: {
                "guessed": set(),
                "wrong": set(),
                "errors": 0,
                "finished": False
            },
            player2: {
                "guessed": set(),
                "wrong": set(),
                "errors": 0,
                "finished": False
            }
        },

        "started_at": time.time()
    }

    user_to_duel[player1] = duel_id
    user_to_duel[player2] = duel_id

    return duel_id


# ==================================================
# СТАРТ РАУНДА
# ==================================================

async def start_round(bot, duel_id):
    duel = duels[duel_id]
    word = duel["word"]

    for user_id in duel["players"]:
        await bot.send_message(
            user_id,
            (
                f"⚔️ Дуэль началась!\n"
                f"Раунд {duel['round']} / {duel['max_rounds']}\n\n"
                f"{masked_word(word, set())}\n\n"
                "✏️ Пиши буквы или слово целиком\n"
                "🏎 Кто первый — забирает раунд!"
            )
        )


# ==================================================
# КОМАНДА /duel
# ==================================================

def register_duel_handlers(dp, bot, words):

    @dp.message(F.text.startswith("/duel"))
    async def duel_command(message: Message):
        user_id = message.from_user.id
        if user_id in user_to_duel:
            await message.answer("⚔️ Ты уже в дуэли. Заверши её или дождись окончания")
            return

        # вызов конкретного игрока
        if len(message.text.split()) > 1:
            await message.answer("❌ Прямые вызовы будут на следующем шаге")
            return

        # поиск случайного соперника
        if duel_queue and duel_queue[0] != user_id:
            opponent = duel_queue.pop(0)

            duel_id = create_duel(user_id, opponent, words)
            await start_round(bot, duel_id)
        else:
            duel_queue.append(user_id)
            await message.answer(
            "⏳ Ожидание соперника для дуэли...\n\n"
            "ℹ️ Любая команда отменит поиск"
        )


# ==================================================
# ПРОВЕРКА: В ДУЭЛИ ЛИ ПОЛЬЗОВАТЕЛЬ
# ==================================================

def get_user_duel(user_id):
    duel_id = user_to_duel.get(user_id)
    if duel_id:
        return duels.get(duel_id)
    return None
async def handle_duel_input(bot, message: Message):
    user_id = message.from_user.id
    duel = get_user_duel(user_id)

    if not duel or not duel["round_active"]:
        return False  # ❗ НЕ дуэль → пусть бот обрабатывает дальше

    text = message.text.lower()
    word = duel["word"]
    game = duel["games"][user_id]

    # попытка угадать слово
    if len(text) > 1:
        if text == word:
            await win_round(bot, duel, user_id)
        else:
            game["errors"] += 1
        await send_state(bot, duel, user_id)
        return True

    # ввод буквы
    letter = text
    if not letter.isalpha():
        return True

    if letter in game["guessed"] or letter in game["wrong"]:
        return True

    if letter in word:
        game["guessed"].add(letter)
    else:
        game["errors"] += 1
        game["wrong"].add(letter)

    # победа
    if "_" not in masked_word(word, game["guessed"]):
        await win_round(bot, duel, user_id)
        return True

    # поражение игрока в раунде
    if game["errors"] >= 6:
        game["finished"] = True
        await bot.send_message(user_id, "💀 Ты выбыл из раунда")
        return True

    await send_state(bot, duel, user_id)
    return True
async def send_state(bot, duel, user_id):
    game = duel["games"][user_id]
    word = duel["word"]

    text = (
        f"⚔️ Дуэль | Раунд {duel['round']}\n\n"
        f"{masked_word(word, game['guessed'])}\n\n"
        f"❌ Ошибки: {game['errors']} / 6\n"
        f"🏆 Счёт: {duel['score'][duel['players'][0]]}"
        f" : {duel['score'][duel['players'][1]]}"
    )

    await bot.send_message(user_id, text)

async def win_round(bot, duel, winner_id):
    if not duel["round_active"]:
        return

    duel["round_active"] = False
    duel["winner_round"] = winner_id
    duel["score"][winner_id] += 1

    for uid in duel["players"]:
        if uid == winner_id:
            await bot.send_message(uid, "🏆 Ты выиграл раунд!")
        else:
            await bot.send_message(uid, "❌ Противник выиграл раунд")

    await next_round(bot, duel)

async def next_round(bot, duel):
    p1, p2 = duel["players"]

    # конец основной серии
    if duel["round"] >= duel["max_rounds"]:
        if duel["score"][p1] != duel["score"][p2]:
            winner = p1 if duel["score"][p1] > duel["score"][p2] else p2
            await bot.send_message(winner, "🏆 Ты выиграл дуэль!")
            await finish_duel(duel)
            return
        else:
            duel["extra"] = True

    duel["round"] += 1
    duel["word"] = generate_word([duel["word"]])  # заменишь на WORDS
    duel["round_active"] = True
    duel["winner_round"] = None

    for uid in duel["players"]:
        duel["games"][uid] = {
            "guessed": set(),
            "wrong": set(),
            "errors": 0,
            "finished": False
        }

    await start_round(bot, duel_id=next(k for k, v in duels.items() if v == duel))

async def finish_duel(duel):
    for uid in duel["players"]:
        user_to_duel.pop(uid, None)

    duel_id = next(k for k, v in duels.items() if v == duel)
    duels.pop(duel_id, None)

def cancel_duel_search(user_id):
    if user_id in duel_queue:
        duel_queue.remove(user_id)
        return True
    return False
