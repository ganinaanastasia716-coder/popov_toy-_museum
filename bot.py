import asyncio
import json
import os
import urllib.parse
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_BASE_URL = os.getenv(
    "WEB_APP_BASE_URL", 
    "https://github.io"
)
STATS_FILE = "workout_stats.json"

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN must be set as the Railway environment variable BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- 📚 НАДЁЖНАЯ БАЗА УПРАЖНЕНИЙ ---
EXERCISES_DATABASE = {
    "Силовая": {
        "верх": [
            {"name": "💪 Отжимания классические"},
            {"name": "💪 Алмазные отжимания"},
            {"name": "💪 Отжимания с широкой постановкой"},
            {"name": "💪 Обратные отжимания от стула"},
            {"name": "🤸 Планка с касанием плеч"},
            {"name": "🤸 Динамическая планка"},
            {"name": "💪 Лодочка (статика на спину)"},
            {"name": "💪 Эксцентрические медленные отжимания"},
            {"name": "💪 Отжимания в пайке"},
            {"name": "💪 Индийские отжимания (Хинду)"},
            {"name": "💪 Отжимания с колен"},
            {"name": "🤸 Планка на локтях с выносом руки"},
            {"name": "💪 Круговые отжимания"},
            {"name": "🤸 Т-планка с разворотом корпуса"},
            {"name": "💪 Лодочка статика"},
            {"name": "🤸 Планка «Сфинкс» на трицепс"},
            {"name": "💪 Отжимания лучника"},
            {"name": "💪 Имитация подтягиваний лежа"}
        ],
        "ноги": [
            {"name": "🦵 Приседания с паузой 3 сек"},
            {"name": "🦵 Выпады назад (поочередно)"},
            {"name": "🦵 Боковые выпады"},
            {"name": "⚡ Болгарские сплит-приседания"},
            {"name": "🔥 Ягодичный мостик на одной ноге"},
            {"name": "🦵 Приседания сумо"},
            {"name": "🔥 Подъемы на носки (на икры)"},
            {"name": "🦵 Стульчик у стены (статика)"},
            {"name": "🦵 Приседания пистолетиком у опоры"},
            {"name": "🦵 Выпады вперед"},
            {"name": "🔥 Классический ягодичный мостик"},
            {"name": "🦵 Диагональные выпады (реверанс)"},
            {"name": "🦵 Приседания с узкой постановкой ног"},
            {"name": "🔥 Подъемы ноги назад на четвереньках"},
            {"name": "🔥 Махи ногой в сторону лежа"},
            {"name": "🦵 Прыжки в полуприседе (статодинамика)"},
            {"name": "🔥 Ягодичный мост с разведением колен"}
        ],
        "пресс": [
            {"name": "🔥 Классические скручивания"},
            {"name": "🔥 Скручивания «Велосипед»"},
            {"name": "💥 Обратные скручивания"},
            {"name": "🤸 Классическая планка на локтях"},
            {"name": "🔥 Упражнение «Книжка» (складка)"},
            {"name": "🤸 Боковая планка"},
            {"name": "💥 Подъемы ног лежа"},
            {"name": "🔥 Русский твист"},
            {"name": "🔥 Скручивания «Ножницы»"},
            {"name": "🤸 Планка «Паук» (колено к локтю)"},
            {"name": "🔥 Касание лодыжек лежа"},
            {"name": "🔥 Поза лодки (статика пресс)"},
            {"name": "💥 Опускание ног поочередно"},
            {"name": "🔥 Косые скручивания лежа"},
            {"name": "🤸 Вакуум живота"},
            {"name": "💥 Вертикальные ножницы ногами"},
            {"name": "🔥 Двойные скручивания"}
        ],
        "все": [
            {"name": "💪 Классические отжимания"},
            {"name": "🦵 Глубокие приседания"},
            {"name": "🔥 Скручивания на пресс"},
            {"name": "🤸 Планка на ладонях"},
            {"name": "💥 Ягодичный мостик двух ног"},
            {"name": "💪 Отжимания в пайке"},
            {"name": "🦵 Диагональные выпады"},
            {"name": "🔥 Русский твист"},
            {"name": "💪 Супермен"},
            {"name": "🦵 Приседания сумо"}
        ]
    },
    "Кардио": {
        "верх": [
            {"name": "💥 Боксерские удары перед собой"},
            {"name": "🤸 Планка с прыжком (Plank Jacks)"},
            {"name": "💥 Бег в планке на руках"},
            {"name": "💪 Взрывные отжимания"},
            {"name": "🤸 Переходы в планке вправо-влево"},
            {"name": "💥 Быстрые удары «апперкот»"},
            {"name": "🤸 Планка с хлопком по груди"},
            {"name": "💥 Имитация прыжков на скакалке руками"},
            {"name": "💪 Отжимания с выпрыгиванием руками"},
            {"name": "🤸 Планка-лягушка"},
            {"name": "💥 Шаги руками вперед-назад из стойки"}
        ],
        "ноги": [
            {"name": "⚡ Выпады с прыжком"},
            {"name": "⚡ Приседания с выпрыгиванием"},
            {"name": "🏃 Бег с высоким подниманием коленей"},
            {"name": "🏃 Захлест голени назад"},
            {"name": "⚡ Прыжки конькобежца"},
            {"name": "🏃 Бег на месте на носочках"},
            {"name": "⚡ Прыжки в приседе вперед-назад"},
            {"name": "⚡ Взрывные выпрыгивания из глубокого седа"},
            {"name": "🏃 Боковые шаги с подпрыжкой"},
            {"name": "⚡ Выпады в стороны в динамике"},
            {"name": "⚡ Прыжки «звездочка»"}
        ],
        "пресс": [
            {"name": "🤸 Быстрый «Горный альпинист»"},
            {"name": "🔥 Динамический русский твист"},
            {"name": "🤸 Боковая планка со скручиванием"},
            {"name": "💥 Подъем коленей к груди в прыжке"},
            {"name": "🔥 Велосипед в быстром темпе"},
            {"name": "🤸 Альпинист по диагонали"},
            {"name": "🔥 Скручивания с хлопком под ногой"},
            {"name": "🤸 Планка с прыжками ногами в стороны"},
            {"name": "💥 Махи «ножницы» на скорость"}
        ],
        "все": [
            {"name": "⚡ Взрывные Бёрпи"},
            {"name": "🏃 Прыжки Джампинг Джек"},
            {"name": "🤸 Горный альпинист быстрый"},
            {"name": "⚡ Прыжки со сменой ног в выпаде"},
            {"name": "🏃 Бег на месте с ускорением"},
            {"name": "⚡ Бёрпи без отжиманий"},
            {"name": "🏃 Прыжки «Лягушка» во все стороны"},
            {"name": "⚡ Прыжки конькобежца широкие"},
            {"name": "🤸 Планка с выпрыгиванием в упор"}
        ]
    },
    "Растяжка": {
        "верх": [
            {"name": "🧘 Растяжка плеч поперек груди"},
            {"name": "🧘 Растяжка трицепса за головой"},
            {"name": "🧘 Замок из рук за спиной"},
            {"name": "🧘 Наклоны шеи в стороны"},
            {"name": "🧘 Растяжка грудных мышц у стены"},
            {"name": "🧘 Поза замка (руки вверх)"},
            {"name": "🧘 Растяжка предплечий и кистей"},
            {"name": "🧘 Округление спины стоя"}
        ],
        "ноги": [
            {"name": "🧘 Наклоны к стопам sitting (складка)"},
            {"name": "🧘 Глубокий выпад (растяжка квадрицепса)"},
            {"name": "🧘 Растяжка «Бабочка»"},
            {"name": "🧘 Наклоны к ногам стоя"},
            {"name": "🧘 Растяжка задней поверхности бедра лежа"},
            {"name": "🧘 Поза голубя (растяжка ягодиц)"},
            {"name": "🧘 Поза полушпагата"},
            {"name": "🧘 Растяжка квадрицепса стоя на одной ноге"}
        ],
        "пресс": [
            {"name": "🧘 Поза кобры (вытяжение живота)"},
            {"name": "🧘 Поза кошки-коровы"},
            {"name": "🧘 Боковое вытягивание корпуса стоя"},
            {"name": "🧘 Скручивание позвоночника лежа"},
            {"name": "🧘 Поза ребенка (расслабление спины)"},
            {"name": "🧘 Поза сфинкса"},
            {"name": "🧘 Боковые наклоны сидя на коленях"},
            {"name": "🧘 Поза моста статическая"}
        ],
        "все": [
            {"name": "🧘 Поза ребенка длительная"},
            {"name": "🧘 Складка сидя к двум ногам"},
            {"name": "🧘 Поза собаки мордой вниз"},
            {"name": "🧘 Растяжка бабочка с наклоном вперед"},
            {"name": "🧘 Поза кобры с поворотом головы"},
            {"name": "🧘 Поза голубя на обе ноги"}
        ]
    },
    "Микс": {
        "верх": [], 
        "ноги": [], 
        "пресс": [], 
        "все": []
    }
}

for zone in ["верх", "ноги", "пресс", "все"]:
    EXERCISES_DATABASE["Микс"][zone] = (
        EXERCISES_DATABASE["Силовая"][zone] + 
        EXERCISES_DATABASE["Кардио"][zone]
    )
# --- 📁 СИСТЕМА ЛОКАЛЬНОЙ СТАТИСТИКОЙ (JSON) ---

def load_stats():
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_stats(stats):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

def get_stats_by_period(user_id: str, days: int):
    stats = load_stats()
    user_id_str = str(user_id)
    if user_id_str not in stats:
        return {"workouts": 0, "calories": 0.0, "minutes": 0}

    cutoff_date = datetime.now() - timedelta(days=days)
    workouts = stats[user_id_str].get("workouts", [])
    filtered = [
        w for w in workouts 
        if datetime.fromisoformat(w["timestamp"]) >= cutoff_date
    ]

    return {
        "workouts": len(filtered),
        "calories": sum(float(w.get("calories", 0)) for w in filtered),
        "minutes": sum(float(w.get("minutes", 0)) for w in filtered)
    }

def calculate_streak(user_id: str, stats: dict):
    user_id_str = str(user_id)
    if user_id_str not in stats or not stats[user_id_str].get("workouts"):
        return 0, 0

    workouts = sorted(
        stats[user_id_str]["workouts"], 
        key=lambda x: x["timestamp"]
    )
    if not workouts:
        return 0, 0

    max_streak = 1
    current_streak = 1

    last_date = datetime.fromisoformat(workouts[0]["timestamp"]).date()
    for i in range(1, len(workouts)):
        current_date = datetime.fromisoformat(workouts[i]["timestamp"]).date()
        diff = (current_date - last_date).days
        if diff == 1:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        elif diff > 1:
            current_streak = 1
        last_date = current_date

    today = datetime.now().date()
    recent_date = datetime.fromisoformat(workouts[-1]["timestamp"]).date()
    if (today - recent_date).days > 1:
        return 0, max_streak

    streak = 1
    cursor = today
    for item in reversed(workouts):
        item_date = datetime.fromisoformat(item["timestamp"]).date()
        if item_date == cursor:
            streak += 1
            cursor -= timedelta(days=1)
        elif (cursor - item_date).days == 1:
            streak += 1
            cursor = item_date
        else:
            break

    return streak - 1, max_streak

def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _duration_seconds(workout_data: dict):
    for key in ("duration_seconds", "elapsed_seconds", "seconds"):
        value = _number(workout_data.get(key), -1)
        if value >= 0:
            return int(round(value)), "actual"

    for key in ("duration_minutes", "elapsed_minutes", "minutes"):
        value = _number(workout_data.get(key), -1)
        if value >= 0:
            return int(round(value * 60)), "actual"

    return 0, "unknown"


def register_user(user: types.User):
    stats = load_stats()
    uid = str(user.id)
    user_data = stats.setdefault(uid, {
        "total_workouts": 0,
        "total_calories": 0.0,
        "total_minutes": 0.0,
        "workouts": [],
        "last_workout_at": None,
        "reminders_sent": [],
        "first_name": user.first_name or "",
        "username": user.username or ""
    })
    user_data.setdefault("total_workouts", 0)
    user_data.setdefault("total_calories", 0.0)
    user_data.setdefault("total_minutes", 0.0)
    user_data.setdefault("workouts", [])
    user_data.setdefault("last_workout_at", None)
    user_data.setdefault("reminders_sent", [])
    user_data["first_name"] = user.first_name or user_data.get("first_name", "")
    user_data["username"] = user.username or user_data.get("username", "")
    save_stats(stats)


def record_workout(user_id: str, workout_data: dict):
    stats = load_stats()
    uid = str(user_id)
    user_data = stats.setdefault(uid, {
        "total_workouts": 0, "total_calories": 0.0, "total_minutes": 0.0,
        "workouts": [], "last_workout_at": None, "reminders_sent": []
    })
    user_data.setdefault("workouts", [])
    user_data.setdefault("reminders_sent", [])

    now = datetime.now().isoformat()
    calories = _number(workout_data.get("calories"), 0.0)
    duration_seconds, duration_source = _duration_seconds(workout_data)
    minutes = round(duration_seconds / 60, 2)

    record = {
        "timestamp": now,
        "action": workout_data.get("action", "workout_finished"),
        "workout_type": workout_data.get("workout_type", workout_data.get("mode", "Тренировка")),
        "mode": workout_data.get("mode", ""),
        "load": workout_data.get("load", ""),
        "focus": workout_data.get("focus", ""),
        "duration_seconds": duration_seconds,
        "formatted_time": workout_data.get("formatted_time", ""),
        "duration_source": duration_source,
        "calories": calories,
        "weight": workout_data.get("weight", ""),
        "age": workout_data.get("age", ""),
        "gender": workout_data.get("gender", ""),
        "height": workout_data.get("height", ""),
        "rounds_completed": workout_data.get("rounds_completed", 0),
        "total_rounds": workout_data.get("total_rounds", 0),
        "work_time": workout_data.get("work_time", 0),
        "rest_time": workout_data.get("rest_time", 0),
        "exercises": workout_data.get("exercises", []),
        "date": workout_data.get("date", now)
    }

    user_data["total_workouts"] = int(user_data.get("total_workouts", 0)) + 1
    user_data["total_calories"] = _number(user_data.get("total_calories"), 0) + calories
    user_data["total_minutes"] = _number(user_data.get("total_minutes"), 0) + minutes
    user_data["last_workout_at"] = now
    user_data["reminders_sent"] = []
    user_data["workouts"].append(record)
    save_stats(stats)
    return record


REMINDER_DAYS = (3, 7, 14, 30)
REMINDER_INTERVAL = 60 * 60

def _last_workout(user_data):
    if user_data.get("last_workout_at"):
        return user_data["last_workout_at"]
    workouts = user_data.get("workouts", [])
    dates = [w.get("timestamp") for w in workouts if w.get("timestamp")]
    return max(dates) if dates else None


def _reminder_text(days, first_name):
    name = f", {first_name}" if first_name else ""
    texts = {
        3: f"👋 {name} уже 3 дня без тренировки.\n\nСамое время вернуться к плану 💪 Сделаем тренировку сегодня?",
        7: f"📅 {name} уже неделя без тренировки.\n\nНе теряем ритм — даже короткая тренировка лучше паузы. 🔥",
        14: f"⚠️ {name} уже 14 дней без тренировки.\n\nДавай мягко вернёмся в режим. Я могу составить тренировку прямо сейчас.",
        30: f"⏰ {name} уже 30 дней без тренировки.\n\nПора возвращаться! Начнём с подходящей нагрузки и без перегруза. 💪"
    }
    return texts[days]


async def reminder_loop():
    while True:
        try:
            stats = load_stats()
            changed = False
            now = datetime.now()
            for uid, user_data in stats.items():
                last = _last_workout(user_data)
                if not last:
                    continue
                try:
                    last_dt = datetime.fromisoformat(last)
                except (TypeError, ValueError):
                    continue
                days = (now - last_dt).days
                sent = set(user_data.get("reminders_sent", []))
                due = [d for d in REMINDER_DAYS if days >= d and d not in sent]
                if not due:
                    continue
                # Отправляем только самое актуальное напоминание, если бот был офлайн.
                day = max(due)
                try:
                    await bot.send_message(int(uid), _reminder_text(day, user_data.get("first_name", "")), reply_markup=get_main_keyboard())
                    user_data.setdefault("reminders_sent", []).extend(due)
                    changed = True
                except Exception as e:
                    print(f"Reminder error for {uid}: {e}")
            if changed:
                save_stats(stats)
        except Exception as e:
            print(f"Reminder loop error: {e}")
        await asyncio.sleep(REMINDER_INTERVAL)

# --- ⚙️ НАСТРОЙКИ КЛАВИАТУР И КОНФИГУРАЦИИ ---

WORKOUT_GOALS = {
    "Силовая": {"ru": "Силовая"},
    "Кардио": {"ru": "Кардио / Жиросжигание"},
    "Растяжка": {"ru": "Растяжка"},
    "Микс": {"ru": "Микс дня (Ganina AI)"}
}

FOCUS_ZONES = {
    "верх": {"emoji": "💪", "name": "Верх тела"},
    "ноги": {"emoji": "🦵", "name": "Ноги и ягодицы"},
    "пресс": {"emoji": "🔥", "name": "Пресс и кор"},
    "все": {"emoji": "🧘", "name": "Все тело"}
}

LOAD_LEVELS = {
    "🟢 Лёгкая": {"met": 3.5, "work_time": 20, "rest_time": 10, "rounds": 6},
    "🟡 Средняя": {"met": 6.0, "work_time": 20, "rest_time": 10, "rounds": 8},
    "🔴 Интенсивная": {"met": 8.5, "work_time": 30, "rest_time": 10, "rounds": 10}
}

def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏋️ Силовая", callback_data="workout_Силовая")],
            [InlineKeyboardButton(text="🏃 Кардио / Жиросжигание", callback_data="workout_Кардио")],
            [InlineKeyboardButton(text="🧘 Растяжка", callback_data="workout_Растяжка")],
            [InlineKeyboardButton(text="🎲 Микс дня (Ganina AI)", callback_data="workout_Микс")],
            [InlineKeyboardButton(text="📊 Моя статистика", callback_data="stats_show")]
        ]
    )
    return keyboard

# --- 🚀 ОСНОВНЫЕ ХЕНДЛЕРЫ БОТА ---

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    register_user(message.from_user)
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        f"Какую тренировку должна составить Ganina сегодня?", 
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    await show_user_stats(message.from_user.id, message)

async def show_user_stats(user_id: int, message_context):
    stats = load_stats()
    user_id_str = str(user_id)

    if user_id_str not in stats or stats[user_id_str].get("total_workouts", 0) == 0:
        text = "📊 **У вас еще нет завершенных тренировок.**\n\nСоздайте первую тренировку прямо сейчас! 💪"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏋️ Создать тренировку", callback_data="workout_Микс")]
            ]
        )
    else:
        user_stats = stats[user_id_str]
        total_workouts = user_stats["total_workouts"]
        total_calories = user_stats["total_calories"]
        total_minutes = user_stats.get("total_minutes", 0)

        week_stats = get_stats_by_period(user_id, 7)
        month_stats = get_stats_by_period(user_id, 30)
        current_streak, max_streak = calculate_streak(user_id, stats)
        streak_emoji = "🔥" if current_streak > 0 else "❄️"

        text = (
            f"📊 **ПОЛНАЯ СТАТИСТИКА**\n\n"
            f"📈 **ВСЕГО:**\n"
            f"   💪 Тренировок: {total_workouts}\n"
            f"   🔥 Сожжено ккал: {total_calories:.0f}\n"
            f"   ⏱️  Минут в работе: {total_minutes}\n"
            f"   📉 Средне за тренировку: {total_calories/total_workouts:.0f} ккал\n\n"
            f"📅 **ЗА НЕДЕЛЮ (7 дней):**\n"
            f"   💪 {week_stats['workouts']} зан. | 🔥 {week_stats['calories']:.0f} ккал | ⏱️ {week_stats['minutes']} мин\n\n"
            f"📆 **ЗА МЕСЯЦ (30 дней):**\n"
            f"   💪 {month_stats['workouts']} зан. | 🔥 {month_stats['calories']:.0f} ккал | ⏱️ {month_stats['minutes']} мин\n\n"
            f"{streak_emoji} **STREAK (Дни подряд):**\n"
            f"   🔥 Текущая серия: {current_streak} дней\n"
            f"   ⭐ Лучший рекорд: {max_streak} дней"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="stats_show")],
                [InlineKeyboardButton(text="🏋️ Новая тренировка", callback_data="workout_Микс")]
            ]
        )

    if isinstance(message_context, types.CallbackQuery):
        await message_context.message.answer(text, reply_markup=keyboard)
    else:
        await message_context.answer(text, reply_markup=keyboard)

@dp.callback_query(F.data == "stats_show")
async def stats_callback(callback: types.CallbackQuery):
    await show_user_stats(callback.from_user.id, callback)
    await callback.answer()
@dp.callback_query(F.data.startswith("workout_"))
async def select_workout_type(callback: types.CallbackQuery):
    goal = callback.data.split("_", 1)[1]
    focus_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💪 Верх тела", callback_data=f"focus_{goal}_верх")],
            [InlineKeyboardButton(text="🦵 Ноги и ягодицы", callback_data=f"focus_{goal}_ноги")],
            [InlineKeyboardButton(text="🔥 Пресс и кор", callback_data=f"focus_{goal}_пресс")],
            [InlineKeyboardButton(text="🧘 Все тело", callback_data=f"focus_{goal}_все")],
            [InlineKeyboardButton(text="← Назад", callback_data="back_to_workout_menu")]
        ]
    )
    goal_name = WORKOUT_GOALS.get(goal, {}).get("ru", goal)
    await callback.message.edit_text(
        f"✨ Вы выбрали: **{goal_name}**\n\n"
        f"На какую зону сосредоточиться?", 
        reply_markup=focus_keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("focus_"))
async def select_focus_zone(callback: types.CallbackQuery):
    parts = callback.data.split("_", 2)
    goal = parts[1]        
    focus_zone = parts[2]  
    
    intensity_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Лёгкая", callback_data=f"intensity_{goal}_{focus_zone}_🟢 Лёгкая")],
            [InlineKeyboardButton(text="🟡 Средняя", callback_data=f"intensity_{goal}_{focus_zone}_🟡 Средняя")],
            [InlineKeyboardButton(text="🔴 Интенсивная", callback_data=f"intensity_{goal}_{focus_zone}_🔴 Интенсивная")],
            [InlineKeyboardButton(text="← Назад", callback_data=f"back_to_focus_{goal}")]
        ]
    )
    focus_name = FOCUS_ZONES.get(focus_zone, {}).get("name", focus_zone)
    await callback.message.edit_text(
        f"🎯 Фокус: **{focus_name}**\n\n"
        f"Выберите уровень интенсивности:", 
        reply_markup=intensity_keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("intensity_"))
async def select_intensity(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    goal = parts[1]        
    focus_zone = parts[2]  
    load_level = "_".join(parts[3:])
    
    await callback.message.edit_text(
        f"⏳ Сборка персонального плана тренировки..."
    )
    
    pool = EXERCISES_DATABASE.get(goal, EXERCISES_DATABASE["Микс"]).get(
        focus_zone, 
        EXERCISES_DATABASE["Микс"]["все"]
    )
    exercises = random.sample(pool, k=min(5, len(pool)))
    
    encoded_exercises = urllib.parse.quote(
        json.dumps(exercises, ensure_ascii=False)
    )
    load_info = LOAD_LEVELS.get(load_level, LOAD_LEVELS["🟡 Средняя"])
    
    params = {
        "workout": encoded_exercises,
        "workout_type": goal,
        "load": load_level,
        "focus": focus_zone,
        "work_time": load_info["work_time"],
        "rest_time": load_info["rest_time"],
        "rounds": load_info["rounds"],
        "met": load_info["met"]
    }
    
    web_app_url = f"{WEB_APP_BASE_URL}?{urllib.parse.urlencode(params)}"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Начать тренировку", web_app=WebAppInfo(url=web_app_url))],
            [InlineKeyboardButton(text="📊 Моя статистика", callback_data="stats_show")],
            [InlineKeyboardButton(text="← Назад", callback_data=f"back_to_intensity_{goal}_{focus_zone}")]
        ]
    )
    
    workout_text = "\n".join(
        [f"{i+1}. {ex['name']}" for i, ex in enumerate(exercises)]
    )
    goal_name = WORKOUT_GOALS.get(goal, {}).get("ru", goal)
    focus_name = FOCUS_ZONES.get(focus_zone, {}).get("name", focus_zone)
    
    await callback.message.answer(
        f"📋 **Ваш случайный план:**\n\n"
        f"**Тип:** {goal_name} • {focus_name}\n"
        f"**Интенсивность:** {load_level}\n\n"
        f"**Упражнения:**\n{workout_text}\n\n"
        f"Нажмите кнопку ниже, чтобы открыть таймер!",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.message(F.web_app_data)
async def handle_web_app_data(message: types.Message):
    try:
        data = json.loads(message.web_app_data.data)
        record = record_workout(message.from_user.id, data)
        current_streak, max_streak = calculate_streak(message.from_user.id, load_stats())

        seconds = int(record.get("duration_seconds", 0))
        mins, secs = divmod(seconds, 60)
        duration = f"{mins} мин" + (f" {secs} сек" if secs else "") if mins else f"{secs} сек"

        await message.answer(
            f"🎉 **Тренировка завершена!**\n\n"
            f"🏋️ **Тип:** {record.get('workout_type', 'Тренировка')}\n"
            f"📌 **Режим:** {record.get('mode', '—')}\n"
            f"💪 **Нагрузка:** {record.get('load', '—')}\n"
            f"🎯 **Фокус:** {record.get('focus', '—')}\n"
            f"⏱️ **Время:** {duration}\n"
            f"🔥 **Калории:** {record.get('calories', 0):.1f} ккал\n"
            f"🔄 **Раунды:** {record.get('rounds_completed', '—')} / {record.get('total_rounds', '—')}\n\n"
            f"🔥 **Серия:** {current_streak} дней (рекорд {max_streak}) 🏆\n\n"
            f"📈 Все показатели сохранены в статистику!",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        print(f"Ошибка сохранения: {e}")
        await message.answer("❌ Ошибка при записи результатов.", reply_markup=get_main_keyboard())

# --- 🔄 НАВИГАЦИЯ НАЗАД ---

@dp.callback_query(F.data == "back_to_workout_menu")
async def back_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Какую тренировку должна составить Ganina сегодня?", 
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("back_to_focus_"))
async def back_focus(callback: types.CallbackQuery):
    goal = callback.data.split("_")[-1]
    focus_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💪 Верх", callback_data=f"focus_{goal}_верх")],
            [InlineKeyboardButton(text="🦵 Ноги", callback_data=f"focus_{goal}_ноги")],
            [InlineKeyboardButton(text="🔥 Пресс", callback_data=f"focus_{goal}_пресс")],
            [InlineKeyboardButton(text="🧘 Все тело", callback_data=f"focus_{goal}_все")],
            [InlineKeyboardButton(text="← Назад", callback_data="back_to_workout_menu")]
        ]
    )
    await callback.message.edit_text(
        "На какую зону сосредоточиться?", 
        reply_markup=focus_keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("back_to_intensity_"))
async def back_intensity(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    goal = parts[3]
    focus_zone = parts[4]
    intensity_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Лёгкая", callback_data=f"intensity_{goal}_{focus_zone}_🟢 Лёгкая")],
            [InlineKeyboardButton(text="🟡 Средняя", callback_data=f"intensity_{goal}_{focus_zone}_🟡 Средняя")],
            [InlineKeyboardButton(text="🔴 Интенсивная", callback_data=f"intensity_{goal}_{focus_zone}_🔴 Интенсивная")],
            [InlineKeyboardButton(text="← Назад", callback_data=f"back_to_focus_{goal}")]
        ]
    )
    await callback.message.edit_text(
        "Выберите уровень интенсивности:", 
        reply_markup=intensity_keyboard
    )
    await callback.answer()

# --- 🚩 ТОЧКА ВХОДА ЗАПУСКА ---

async def main():
    print("🤖 Бот запущен...")
    reminder_task = asyncio.create_task(reminder_loop())
    try:
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
