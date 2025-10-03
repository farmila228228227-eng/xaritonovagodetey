import os
import asyncio
import logging
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions

logging.basicConfig(level=logging.INFO)

# ----------------- НАСТРОЙКИ -----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в переменных окружения. Добавь его в Secrets Replit.")
OWNER_ID = 7322925570  # твой ID
DATA_FILE = Path("data.json")
MUTE_DEFAULT_MINUTES = 30
# -------------------------------------------

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# pending actions для админ-панели
pending_actions: Dict[int, Dict[str, Any]] = {}

# ----------------- УТИЛИТЫ ------------------
def load_data() -> Dict[str, Any]:
    if not DATA_FILE.exists():
        data = {
            "admins": [],
            "forbidden_words": [],
            "mute_minutes": MUTE_DEFAULT_MINUTES,
            "allowed_links": []
        }
        save_data(data)
        return data
    with DATA_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data: Dict[str, Any]) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_owner_or_admin(user_id: int, data: Dict[str, Any]) -> bool:
    return user_id == OWNER_ID or user_id in data.get("admins", [])

def normalize_word(w: str) -> str:
    return w.strip().lower()

def build_admin_panel(data: Dict[str, Any]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить слово", callback_data="add_word"),
            InlineKeyboardButton(text="➖ Удалить слово", callback_data="remove_word"),
        ],
        [
            InlineKeyboardButton(text="⏱️ Установить длительность мута", callback_data="set_mute"),
            InlineKeyboardButton(text="📜 Список слов", callback_data="list_words"),
        ],
        [
            InlineKeyboardButton(text="➕ Разрешить ссылку", callback_data="add_allow_link"),
            InlineKeyboardButton(text="➖ Удалить разрешённую ссылку", callback_data="remove_allow_link"),
        ],
        [
            InlineKeyboardButton(text="👥 Управление админами", callback_data="manage_admins"),
            InlineKeyboardButton(text="💾 Сохранить", callback_data="save_settings"),
        ]
    ])
    return kb

def build_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])

def extract_domains_from_text(text: str) -> List[str]:
    urls = re.findall(r"(https?://[^\s]+)", text)
    domains = []
    for u in urls:
        m = re.match(r"https?://([^/]+)", u)
        if m:
            domains.append(m.group(1).lower())
    return domains

# Загружаем сохранённые данные
data = load_data()

# ----------------- КОМАНДЫ ------------------

@dp.message(Command(commands=["start", "help"]))
async def cmd_start(message: types.Message):
    if message.chat.type == "private" and not is_owner_or_admin(message.from_user.id, data):
        return
    await message.reply("Привет! Я модератор-бот. Используйте /dante для списка команд.")

@dp.message(Command(commands=["dante"]))
async def cmd_dante(message: types.Message):
    if message.chat.type == "private" and not is_owner_or_admin(message.from_user.id, data):
        return
    text = (
        "📌 Список команд бота:\n\n"
        "/admin - Админ-панель (в ЛС владельца/админов)\n"
        "/dante - показать этот список\n\n"
        "В группах:\n"
        "- Мут за запрещённые слова\n"
        "- Бан за запрещённые ссылки\n"
        "- Белый список ссылок\n"
        "- Поддержка топиков и обычных чатов\n"
    )
    await message.reply(text)

@dp.message(Command(commands=["admin"]))
async def cmd_admin(message: types.Message):
    if message.chat.type != "private":
        await message.reply("⚠️ Используй /admin только в ЛС.")
        return
    if not is_owner_or_admin(message.from_user.id, data):
        return
    kb = build_admin_panel(data)
    await message.answer("⚙️ Админ-панель:", reply_markup=kb)

# ----------------- АНТИ-СПАМ ------------------

@dp.message()
async def moderate_message(message: types.Message):
    if message.from_user.is_bot:
        return
    if message.chat.type == "private":
        return

    chat_id = message.chat.id
    user = message.from_user
    text = message.text or message.caption or ""
    text_lower = (text or "").lower()

    # Проверка ссылок
    if "http://" in text_lower or "https://" in text_lower:
        domains = extract_domains_from_text(text_lower)
        allowed = data.get("allowed_links", [])
        if not any(any(a in d for a in allowed) for d in domains):
            try:
                await bot.delete_message(chat_id, message.message_id)
                await bot.ban_chat_member(chat_id, user.id)
            except:
                pass
            who = f"@{user.username}" if user.username else f"{user.full_name}/{user.id}"
            await bot.send_message(chat_id, f"🚫 Пользователь {who} отправил запрещённую ссылку и был забанен.")
            return

    # Проверка слов
    for w in data.get("forbidden_words", []):
        if re.search(rf"\b{re.escape(w)}\b", text_lower):
            try:
                await bot.delete_message(chat_id, message.message_id)
            except:
                pass
            until = datetime.utcnow() + timedelta(minutes=data.get("mute_minutes", MUTE_DEFAULT_MINUTES))
            try:
                await bot.restrict_chat_member(chat_id, user.id, ChatPermissions(can_send_messages=False), until_date=until)
            except:
                pass
            who = f"@{user.username}" if user.username else f"{user.full_name}/{user.id}"
            await bot.send_message(chat_id, f"🔇 Пользователь {who} написал запрещённое слово и получил мут.")
            return

# ----------------- ВЫКЛЮЧЕНИЕ ------------------
async def shutdown():
    save_data(data)
    try:
        await bot.session.close()
    except:
        pass
