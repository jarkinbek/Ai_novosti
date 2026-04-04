from dotenv import load_dotenv
import os
import asyncio
import logging
import re
import sys
import feedparser
import httpx
from datetime import datetime
import requests
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
from dotenv import load_dotenv
import os
import asyncio
import logging
import re
import sys
import feedparser
import httpx
from datetime import datetime
import requests
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
def call_ai(prompt):
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek/deepseek-chat",
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=20
        )

        data = response.json()

        # 🔴 если ошибка
        if "error" in data:
            print("API ERROR:", data["error"])
            return "❌ Ошибка AI: нет баланса или неверный ключ"

        return data["choices"][0]["message"]["content"]

    except Exception as e:
        print("AI error:", e)
        return "⚠️ AI ошибка"

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, BotCommand
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import Database
from texts import get_text, CATEGORIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = Database()


NEWS_PER_PAGE = 3

# ── FSM ───────────────────────────────────────────────────────────────────────
class ChatState(StatesGroup):
    chatting = State()

class SearchState(StatesGroup):
    waiting_query = State()

# ── Keyboards ─────────────────────────────────────────────────────────────────
def main_menu(lang: str) -> InlineKeyboardMarkup:
    t = get_text(lang)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t["btn_news"],   callback_data="news_menu"),
            InlineKeyboardButton(text=t["btn_ai"],     callback_data="ai_chat"),
        ],
        [
            InlineKeyboardButton(text=t["btn_search"], callback_data="search"),
            InlineKeyboardButton(text=t["btn_digest"], callback_data="digest"),
        ],
        [
            InlineKeyboardButton(text=t["btn_trends"], callback_data="trends"),
            InlineKeyboardButton(text=t["btn_quiz"],   callback_data="quiz"),
        ],
        [
            InlineKeyboardButton(text=t["btn_settings"], callback_data="settings"),
        ],
    ])

def categories_kb(lang: str) -> InlineKeyboardMarkup:
    t = get_text(lang)
    rows = []
    cats = list(CATEGORIES.items())
    for i in range(0, len(cats), 2):
        row = []
        for key, emoji in cats[i:i+2]:
            row.append(InlineKeyboardButton(
                text=f"{emoji} {t.get('cat_' + key, key.capitalize())}",
                callback_data=f"cat_{key}_0"
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton(text=t["btn_back"], callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский",  callback_data="set_lang_ru"),
            InlineKeyboardButton(text="🇺🇿 O'zbek",   callback_data="set_lang_uz"),
        ]
    ])

def back_kb(lang: str, back_to: str = "main_menu") -> InlineKeyboardMarkup:
    t = get_text(lang)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_back"], callback_data=back_to)]
    ])

# ── Helpers ───────────────────────────────────────────────────────────────────
def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()

async def fetch_news(category: str) -> list[dict]:
    from config import RSS_FEEDS
    feeds = RSS_FEEDS.get(category, RSS_FEEDS["politics"])
    articles = []
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        for url in feeds:
            try:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                feed = feedparser.parse(resp.text)
                for entry in feed.entries[:5]:
                    summary = strip_html(entry.get("summary", entry.get("description", "")))[:600]
                    content_list = entry.get("content", [])
                    full = strip_html(content_list[0].get("value", "") if content_list else "")[:3500] or summary
                    pub = entry.get("published", "")
                    articles.append({
                        "id":        str(abs(hash(entry.get("link", "") + entry.get("title", "")))),
                        "title":     entry.get("title", "Без заголовка")[:160],
                        "summary":   summary,
                        "full":      full,
                        "link":      entry.get("link", ""),
                        "source":    feed.feed.get("title", "Unknown"),
                        "published": pub[:16] if pub else "",
                    })
            except Exception as e:
                logger.warning(f"RSS error {url}: {e}")
    seen, result = set(), []
    for a in articles:
        if a["id"] not in seen:
            seen.add(a["id"])
            result.append(a)
    return result

def save_articles(articles: list[dict]):
    for a in articles:
        db.save_article(a["id"], a)

def format_card(article: dict, idx: int, page: int, total: int, lang: str) -> str:
    t   = get_text(lang)
    num = page * NEWS_PER_PAGE + idx + 1
    return (
        f"<i>{t.get('news_count', 'Новость')} {num}/{total}</i>\n\n"
        f"<b>📰 {esc(article['title'])}</b>\n\n"
        f"{esc(article['summary'][:280])}{'…' if len(article['summary']) > 280 else ''}\n\n"
        f"<i>🏛 {esc(article.get('source',''))}  •  🕐 {article.get('published','')}</i>"
    )


# ── /start ────────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("🌍 <b>Выберите язык / Tilni tanlang:</b>",
                             reply_markup=lang_kb(), parse_mode="HTML")
    else:
        lang = user["lang"]
        t = get_text(lang)
        await message.answer(t["welcome"], reply_markup=main_menu(lang), parse_mode="HTML")

@dp.callback_query(F.data.startswith("set_lang_"))
async def set_language(cb: CallbackQuery):
    lang = cb.data.replace("set_lang_", "")
    u = cb.from_user
    db.save_user(u.id, {"id": u.id, "lang": lang, "name": u.full_name, "joined": datetime.now().isoformat()})
    t = get_text(lang)
    await cb.message.edit_text(t["welcome"], reply_markup=main_menu(lang), parse_mode="HTML")

@dp.callback_query(F.data == "main_menu")
async def go_main(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = db.get_user(cb.from_user.id)["lang"]
    t = get_text(lang)
    await cb.message.edit_text(t["welcome"], reply_markup=main_menu(lang), parse_mode="HTML")

# ── News ──────────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "news_menu")
async def news_menu(cb: CallbackQuery):
    lang = db.get_user(cb.from_user.id)["lang"]
    t = get_text(lang)
    await cb.message.edit_text(t["choose_category"], reply_markup=categories_kb(lang), parse_mode="HTML")

@dp.callback_query(F.data.startswith("cat_"))
async def show_category(cb: CallbackQuery):
    parts    = cb.data.split("_", 2)
    category = parts[1]
    page     = int(parts[2]) if len(parts) > 2 else 0
    lang     = db.get_user(cb.from_user.id)["lang"]
    t        = get_text(lang)

    cached = db.get_category_cache(category)
    if not cached or page == 0:
        try:
            await cb.message.edit_text(f"⏳ <b>{t['loading']}</b>", parse_mode="HTML")
        except Exception:
            pass
        articles = await fetch_news(category)
        save_articles(articles)
        db.save_category_cache(category, [a["id"] for a in articles])
    else:
        articles = [db.get_article(aid) for aid in cached if db.get_article(aid)]

    if not articles:
        await cb.message.edit_text(t["no_news"], reply_markup=back_kb(lang, "news_menu"), parse_mode="HTML")
        return

    total = len(articles)
    start = page * NEWS_PER_PAGE
    chunk = articles[start: start + NEWS_PER_PAGE]

    cards_text = ""
    for idx, article in enumerate(chunk):
        cards_text += format_card(article, idx, page, total, lang)
        if idx < len(chunk) - 1:
            cards_text += "\n\n" + "─" * 30 + "\n\n"

    kb_rows = []
    for idx, article in enumerate(chunk):
        num = page * NEWS_PER_PAGE + idx + 1
        kb_rows.append([
            InlineKeyboardButton(
                text=f"📖 #{num} {t['btn_read_full']}",
                callback_data=f"read_{article['id']}_{page}_{category}"
            ),
            InlineKeyboardButton(text="🤖 AI", callback_data=f"analyze_{article['id']}"),
        ])
        kb_rows.append([
            InlineKeyboardButton(
                text=f"🔄 {t['btn_translate']} #{num}",
                callback_data=f"translate_{article['id']}"
            ),
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=f"◀️ {t['btn_prev']}", callback_data=f"cat_{category}_{page-1}"))
    if start + NEWS_PER_PAGE < total:
        nav.append(InlineKeyboardButton(text=f"{t['btn_next']} ▶️", callback_data=f"cat_{category}_{page+1}"))
    if nav:
        kb_rows.append(nav)
    kb_rows.append([InlineKeyboardButton(text=t["btn_back"], callback_data="news_menu")])

    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    try:
        await cb.message.edit_text(cards_text[:4096], reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Edit failed: {e}")
        await bot.send_message(cb.from_user.id, cards_text[:4096], reply_markup=kb, parse_mode="HTML")

# ── Read Full ──────────────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("read_"))
async def read_full(cb: CallbackQuery):
    parts      = cb.data.split("_", 3)
    article_id = parts[1]
    page       = int(parts[2]) if len(parts) > 2 else 0
    category   = parts[3] if len(parts) > 3 else "politics"
    lang       = db.get_user(cb.from_user.id)["lang"]
    t          = get_text(lang)
    article    = db.get_article(article_id)

    if not article:
        await cb.answer(t["article_not_found"], show_alert=True)
        return

    content = article.get("full") or article.get("summary", "")
    text = (
        f"📄 <b>{esc(article['title'])}</b>\n"
        f"<i>🏛 {esc(article.get('source',''))}  •  🕐 {article.get('published','')}</i>\n\n"
        f"{'─'*28}\n\n{esc(content[:3500])}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🤖 {t['btn_ai_analyze']}", callback_data=f"analyze_{article_id}"),
            InlineKeyboardButton(text=f"🔄 {t['btn_translate']}",  callback_data=f"translate_{article_id}"),
        ],
        [InlineKeyboardButton(text=t["btn_back"], callback_data=f"cat_{category}_{page}")],
    ])
    try:
        await cb.message.edit_text(text[:4096], reply_markup=kb, parse_mode="HTML")
    except Exception:
        await bot.send_message(cb.from_user.id, text[:4096], reply_markup=kb, parse_mode="HTML")

# ── Translate ──────────────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("translate_"))
async def translate_article(cb: CallbackQuery):
    article_id = cb.data.replace("translate_", "")
    lang       = db.get_user(cb.from_user.id)["lang"]
    t          = get_text(lang)
    article    = db.get_article(article_id)
    if not article:
        await cb.answer(t["article_not_found"], show_alert=True)
        return
    await cb.answer()
    msg = await bot.send_message(cb.from_user.id, f"🔄 <b>{t['translating']}...</b>", parse_mode="HTML")
    target = "узбекский язык (латиница)" if lang == "uz" else "русский язык"
    prompt = (
        f"Переведи на {target}. Только перевод без пояснений.\n\n"
        f"Заголовок: {article['title']}\n\nТекст: {article.get('summary', '')}"
    )
    result =  call_ai(prompt)
    kb = back_kb(lang)
    await msg.edit_text(
        f"🔄 <b>{t['translation_result']}</b>\n<i>🏛 {esc(article.get('source',''))}</i>\n\n{'─'*28}\n\n{esc(result[:3800])}",
        reply_markup=kb, parse_mode="HTML"
    )

# ── AI Analyze ────────────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("analyze_"))
async def analyze_article(cb: CallbackQuery):
    article_id = cb.data.replace("analyze_", "")
    lang       = db.get_user(cb.from_user.id)["lang"]
    t          = get_text(lang)
    article    = db.get_article(article_id)
    if not article:
        await cb.answer(t["article_not_found"], show_alert=True)
        return
    await cb.answer()
    msg = await bot.send_message(cb.from_user.id, f"🤖 <b>{t['ai_analyzing']}...</b>", parse_mode="HTML")
    lang_instr = "Отвечай на русском языке." if lang == "ru" else "O'zbek tilida javob ber."
    prompt = (
        f"Проанализируй новость:\n\nЗаголовок: {article['title']}\n"
        f"Содержание: {article.get('summary', '')}\n\n{lang_instr}\n\n"
        f"Структура:\n📊 Суть события — 2-3 предложения\n"
        f"🌍 Геополитическое влияние\n💰 Экономические последствия\n"
        f"🔮 Прогноз развития\n⚖️ Оценка достоверности"
    )
    full_prompt = (
    "Ты — опытный политический и экономический аналитик. "
    "Объективен, без предвзятости.\n\n" + prompt
)

    result = call_ai(full_prompt)
    kb = back_kb(lang)
    await msg.edit_text(
        f"🤖 <b>AI Анализ</b>\n{'─'*28}\n\n{esc(result[:4000])}",
        reply_markup=kb, parse_mode="HTML"
    )

# ── AI Chat ───────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "ai_chat")
async def start_ai_chat(cb: CallbackQuery, state: FSMContext):
    lang = db.get_user(cb.from_user.id)["lang"]
    t    = get_text(lang)
    await state.set_state(ChatState.chatting)
    await state.update_data(history=[])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_stop_chat"], callback_data="main_menu")]
    ])
    await cb.message.edit_text(t["ai_chat_start"], reply_markup=kb, parse_mode="HTML")

@dp.message(ChatState.chatting)
async def ai_chat_message(message: Message, state: FSMContext):
    lang = db.get_user(message.from_user.id)["lang"]
    t = get_text(lang)
    data = await state.get_data()
    history = data.get("history", [])

    history.append({"role": "user", "content": message.text})
    if len(history) > 20:
        history = history[-20:]

    thinking = await message.answer(f"🤔 <i>{t['ai_thinking']}...</i>", parse_mode="HTML")

    lang_instr = "Отвечай на русском языке." if lang == "ru" else "O'zbek tilida javob ber."
    system = f"Ты — эксперт по мировой политике и экономике. {lang_instr} Структурируй ответы с эмодзи."

    try:
        full_prompt = system + "\n\n"

        for msg in history:
            full_prompt += f"{msg['role']}: {msg['content']}\n"

        reply = call_ai(full_prompt)

        history.append({"role": "assistant", "content": reply})
        await state.update_data(history=history)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_stop_chat"], callback_data="main_menu")]
        ])

        await thinking.edit_text(
            esc(reply)[:4096],
            reply_markup=kb,
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"AI chat error: {e}")
        await thinking.edit_text(f"⚠️ {t['ai_error']}")

# ── Digest ────────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "digest")
async def daily_digest(cb: CallbackQuery):
    lang = db.get_user(cb.from_user.id)["lang"]
    t    = get_text(lang)
    await cb.message.edit_text(f"⏳ <b>{t['digest_loading']}</b>", parse_mode="HTML")
    all_articles = []
    for cat in ["politics", "economy", "world"]:
        arts = await fetch_news(cat)
        all_articles.extend(arts[:3])
    save_articles(all_articles)
    headlines = "\n".join([f"- {a['title']}" for a in all_articles[:10]])
    lang_instr = "Отвечай на русском языке." if lang == "ru" else "O'zbek tilida javob ber."
    prompt = (
        f"Составь дайджест главных мировых новостей:\n\n{headlines}\n\n{lang_instr}\n\n"
        f"Формат:\n🌍 ДАЙДЖЕСТ ДНЯ\n\n📌 [3-4 события по 2-3 предложения]\n\n"
        f"📊 Общая картина: [абзац]\n\n⭐ Главный вывод: [одно предложение]"
    )
    digest =  call_ai(prompt)
    date_str = datetime.now().strftime("%d.%m.%Y")
    await cb.message.edit_text(
        f"📅 <b>{date_str}</b>\n\n{esc(digest)}",
        reply_markup=back_kb(lang), parse_mode="HTML"
    )

# ── Trends ────────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "trends")
async def show_trends(cb: CallbackQuery):
    lang = db.get_user(cb.from_user.id)["lang"]
    t    = get_text(lang)
    await cb.message.edit_text(f"⏳ <b>{t['trends_loading']}</b>", parse_mode="HTML")
    articles = []
    for cat in ["politics", "economy", "world", "asia", "europe"]:
        arts = await fetch_news(cat)
        articles.extend(arts[:2])
    save_articles(articles)
    headlines = "\n".join([f"- {a['title']}" for a in articles[:12]])
    lang_instr = "Отвечай на русском языке." if lang == "ru" else "O'zbek tilida javob ber."
    prompt = (
        f"На основе заголовков определи тренды:\n\n{headlines}\n\n{lang_instr}\n\n"
        f"🔥 ТОП-3 горячих темы (с объяснением)\n📈 Экономические тренды\n"
        f"🌐 Геополитические тренды\n🔭 На что обратить внимание"
    )
    result =  call_ai(prompt)
    await cb.message.edit_text(esc(result)[:4096], reply_markup=back_kb(lang), parse_mode="HTML")

# ── Quiz ──────────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "quiz")
async def start_quiz(cb: CallbackQuery):
    lang = db.get_user(cb.from_user.id)["lang"]
    t    = get_text(lang)
    await cb.message.edit_text(f"⏳ <b>{t['quiz_loading']}</b>", parse_mode="HTML")
    lang_instr = "На русском языке." if lang == "ru" else "O'zbek tilida."
    prompt = (
        f"Придумай вопрос-викторину по мировой политике/экономике. {lang_instr}\n\n"
        f"СТРОГИЙ ФОРМАТ (ничего лишнего):\n"
        f"ВОПРОС: [вопрос]\n"
        f"A) [вариант]\nB) [вариант]\nC) [вариант]\nD) [вариант]\n"
        f"ОТВЕТ: [только буква]\nПОЯСНЕНИЕ: [2-3 предложения]"
    )
    raw   =  call_ai(prompt)
    lines = raw.strip().split("\n")
    question = ""; options = []; answer = ""; explanation = ""
    for line in lines:
        line = line.strip()
        if line.startswith("ВОПРОС:") or line.startswith("SAVOL:"):
            question = line.split(":", 1)[1].strip()
        elif line[:2] in ("A)", "B)", "C)", "D)"):
            options.append(line)
        elif line.startswith("ОТВЕТ:") or line.startswith("JAVOB:"):
            answer = line.split(":", 1)[1].strip()
        elif line.startswith("ПОЯСНЕНИЕ:") or line.startswith("IZOH:"):
            explanation = line.split(":", 1)[1].strip()

    if not question or not options:
        await cb.message.edit_text(t["quiz_error"], reply_markup=back_kb(lang), parse_mode="HTML")
        return

    opts_text = "\n".join(options)
    ans_data  = f"{answer}||{esc(explanation)}"
    text = f"🧠 <b>{t['quiz_title']}</b>\n\n{'─'*28}\n\n❓ {esc(question)}\n\n{esc(opts_text)}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="A", callback_data=f"quiz_ans_A||{ans_data}"),
            InlineKeyboardButton(text="B", callback_data=f"quiz_ans_B||{ans_data}"),
        ],
        [
            InlineKeyboardButton(text="C", callback_data=f"quiz_ans_C||{ans_data}"),
            InlineKeyboardButton(text="D", callback_data=f"quiz_ans_D||{ans_data}"),
        ],
        [InlineKeyboardButton(text=t["btn_back"], callback_data="main_menu")],
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("quiz_ans_"))
async def quiz_answer(cb: CallbackQuery):
    lang  = db.get_user(cb.from_user.id)["lang"]
    t     = get_text(lang)
    raw   = cb.data.replace("quiz_ans_", "")
    parts = raw.split("||", 2)
    chosen      = parts[0]
    correct     = parts[1] if len(parts) > 1 else "?"
    explanation = parts[2] if len(parts) > 2 else ""
    if chosen == correct:
        result_emoji = "✅"; result_text = t["quiz_correct"]
    else:
        result_emoji = "❌"; result_text = t["quiz_wrong"].replace("{ans}", correct)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_new_quiz"], callback_data="quiz")],
        [InlineKeyboardButton(text=t["btn_back"],     callback_data="main_menu")],
    ])
    await cb.message.edit_text(
        f"{result_emoji} <b>{result_text}</b>\n\n💡 {esc(explanation)}",
        reply_markup=kb, parse_mode="HTML"
    )

# ── Search ────────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "search")
async def start_search(cb: CallbackQuery, state: FSMContext):
    lang = db.get_user(cb.from_user.id)["lang"]
    t    = get_text(lang)
    await state.set_state(SearchState.waiting_query)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_back"], callback_data="main_menu")]
    ])
    await cb.message.edit_text(t["search_prompt"], reply_markup=kb, parse_mode="HTML")

@dp.message(SearchState.waiting_query)
async def do_search(message: Message, state: FSMContext):
    lang  = db.get_user(message.from_user.id)["lang"]
    t     = get_text(lang)
    query = message.text.strip()
    await state.clear()
    thinking = await message.answer(f"🔍 <i>{t['searching']}...</i>", parse_mode="HTML")
    lang_instr = "Отвечай на русском языке." if lang == "ru" else "O'zbek tilida javob ber."
    prompt = (
        f'Пользователь ищет: "{query}"\n\n{lang_instr}\n\n'
        f"Дай экспертный ответ в контексте мировой политики и экономики:\n"
        f"📌 Суть темы\n🌍 Текущее положение\n🔑 Ключевые игроки\n📈 Последние тенденции"
    )
    result =  call_ai(prompt)
    await thinking.edit_text(
        f"🔍 <b>{esc(query)}</b>\n{'─'*28}\n\n{esc(result[:4000])}",
        reply_markup=back_kb(lang), parse_mode="HTML"
    )

# ── Settings ──────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "settings")
async def settings(cb: CallbackQuery):
    lang = db.get_user(cb.from_user.id)["lang"]
    t    = get_text(lang)
    user = db.get_user(cb.from_user.id)
    cur_lang = "🇷🇺 Русский" if lang == "ru" else "🇺🇿 O'zbek"
    text = (
        f"⚙️ <b>{t['settings_title']}</b>\n\n"
        f"👤 {t['settings_name']}: <b>{esc(cb.from_user.full_name)}</b>\n"
        f"🌐 {t['settings_lang']}: <b>{cur_lang}</b>\n"
        f"📅 {t['settings_joined']}: <b>{user.get('joined','')[:10]}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_change_lang"], callback_data="change_lang")],
        [InlineKeyboardButton(text=t["btn_back"],        callback_data="main_menu")],
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "change_lang")
async def change_lang(cb: CallbackQuery):
    await cb.message.edit_text(
        "🌍 <b>Выберите язык / Tilni tanlang:</b>",
        reply_markup=lang_kb(), parse_mode="HTML"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    u    = db.get_user(message.from_user.id)
    lang = u["lang"] if u else "ru"
    t    = get_text(lang)
    await message.answer(t["help_text"], reply_markup=main_menu(lang), parse_mode="HTML")

# ── Main ──────────────────────────────────────────────────────────────────────
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню / Bosh menyu"),
        BotCommand(command="help",  description="Помощь / Yordam"),
    ])

async def main():
    await set_commands()
    logger.info("🤖 PolNews AI Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, BotCommand
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import Database
from texts import get_text, CATEGORIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = Database()


NEWS_PER_PAGE = 3

# ── FSM ───────────────────────────────────────────────────────────────────────
class ChatState(StatesGroup):
    chatting = State()

class SearchState(StatesGroup):
    waiting_query = State()

# ── Keyboards ─────────────────────────────────────────────────────────────────
def main_menu(lang: str) -> InlineKeyboardMarkup:
    t = get_text(lang)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t["btn_news"],   callback_data="news_menu"),
            InlineKeyboardButton(text=t["btn_ai"],     callback_data="ai_chat"),
        ],
        [
            InlineKeyboardButton(text=t["btn_search"], callback_data="search"),
            InlineKeyboardButton(text=t["btn_digest"], callback_data="digest"),
        ],
        [
            InlineKeyboardButton(text=t["btn_trends"], callback_data="trends"),
            InlineKeyboardButton(text=t["btn_quiz"],   callback_data="quiz"),
        ],
        [
            InlineKeyboardButton(text=t["btn_settings"], callback_data="settings"),
        ],
    ])

def categories_kb(lang: str) -> InlineKeyboardMarkup:
    t = get_text(lang)
    rows = []
    cats = list(CATEGORIES.items())
    for i in range(0, len(cats), 2):
        row = []
        for key, emoji in cats[i:i+2]:
            row.append(InlineKeyboardButton(
                text=f"{emoji} {t.get('cat_' + key, key.capitalize())}",
                callback_data=f"cat_{key}_0"
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton(text=t["btn_back"], callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский",  callback_data="set_lang_ru"),
            InlineKeyboardButton(text="🇺🇿 O'zbek",   callback_data="set_lang_uz"),
        ]
    ])

def back_kb(lang: str, back_to: str = "main_menu") -> InlineKeyboardMarkup:
    t = get_text(lang)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_back"], callback_data=back_to)]
    ])

# ── Helpers ───────────────────────────────────────────────────────────────────
def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()

async def fetch_news(category: str) -> list[dict]:
    from config import RSS_FEEDS
    feeds = RSS_FEEDS.get(category, RSS_FEEDS["politics"])
    articles = []
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        for url in feeds:
            try:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                feed = feedparser.parse(resp.text)
                for entry in feed.entries[:5]:
                    summary = strip_html(entry.get("summary", entry.get("description", "")))[:600]
                    content_list = entry.get("content", [])
                    full = strip_html(content_list[0].get("value", "") if content_list else "")[:3500] or summary
                    pub = entry.get("published", "")
                    articles.append({
                        "id":        str(abs(hash(entry.get("link", "") + entry.get("title", "")))),
                        "title":     entry.get("title", "Без заголовка")[:160],
                        "summary":   summary,
                        "full":      full,
                        "link":      entry.get("link", ""),
                        "source":    feed.feed.get("title", "Unknown"),
                        "published": pub[:16] if pub else "",
                    })
            except Exception as e:
                logger.warning(f"RSS error {url}: {e}")
    seen, result = set(), []
    for a in articles:
        if a["id"] not in seen:
            seen.add(a["id"])
            result.append(a)
    return result

def save_articles(articles: list[dict]):
    for a in articles:
        db.save_article(a["id"], a)

def format_card(article: dict, idx: int, page: int, total: int, lang: str) -> str:
    t   = get_text(lang)
    num = page * NEWS_PER_PAGE + idx + 1
    return (
        f"<i>{t.get('news_count', 'Новость')} {num}/{total}</i>\n\n"
        f"<b>📰 {esc(article['title'])}</b>\n\n"
        f"{esc(article['summary'][:280])}{'…' if len(article['summary']) > 280 else ''}\n\n"
        f"<i>🏛 {esc(article.get('source',''))}  •  🕐 {article.get('published','')}</i>"
    )


# ── /start ────────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("🌍 <b>Выберите язык / Tilni tanlang:</b>",
                             reply_markup=lang_kb(), parse_mode="HTML")
    else:
        lang = user["lang"]
        t = get_text(lang)
        await message.answer(t["welcome"], reply_markup=main_menu(lang), parse_mode="HTML")

@dp.callback_query(F.data.startswith("set_lang_"))
async def set_language(cb: CallbackQuery):
    lang = cb.data.replace("set_lang_", "")
    u = cb.from_user
    db.save_user(u.id, {"id": u.id, "lang": lang, "name": u.full_name, "joined": datetime.now().isoformat()})
    t = get_text(lang)
    await cb.message.edit_text(t["welcome"], reply_markup=main_menu(lang), parse_mode="HTML")

@dp.callback_query(F.data == "main_menu")
async def go_main(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = db.get_user(cb.from_user.id)["lang"]
    t = get_text(lang)
    await cb.message.edit_text(t["welcome"], reply_markup=main_menu(lang), parse_mode="HTML")

# ── News ──────────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "news_menu")
async def news_menu(cb: CallbackQuery):
    lang = db.get_user(cb.from_user.id)["lang"]
    t = get_text(lang)
    await cb.message.edit_text(t["choose_category"], reply_markup=categories_kb(lang), parse_mode="HTML")

@dp.callback_query(F.data.startswith("cat_"))
async def show_category(cb: CallbackQuery):
    parts    = cb.data.split("_", 2)
    category = parts[1]
    page     = int(parts[2]) if len(parts) > 2 else 0
    lang     = db.get_user(cb.from_user.id)["lang"]
    t        = get_text(lang)

    cached = db.get_category_cache(category)
    if not cached or page == 0:
        try:
            await cb.message.edit_text(f"⏳ <b>{t['loading']}</b>", parse_mode="HTML")
        except Exception:
            pass
        articles = await fetch_news(category)
        save_articles(articles)
        db.save_category_cache(category, [a["id"] for a in articles])
    else:
        articles = [db.get_article(aid) for aid in cached if db.get_article(aid)]

    if not articles:
        await cb.message.edit_text(t["no_news"], reply_markup=back_kb(lang, "news_menu"), parse_mode="HTML")
        return

    total = len(articles)
    start = page * NEWS_PER_PAGE
    chunk = articles[start: start + NEWS_PER_PAGE]

    cards_text = ""
    for idx, article in enumerate(chunk):
        cards_text += format_card(article, idx, page, total, lang)
        if idx < len(chunk) - 1:
            cards_text += "\n\n" + "─" * 30 + "\n\n"

    kb_rows = []
    for idx, article in enumerate(chunk):
        num = page * NEWS_PER_PAGE + idx + 1
        kb_rows.append([
            InlineKeyboardButton(
                text=f"📖 #{num} {t['btn_read_full']}",
                callback_data=f"read_{article['id']}_{page}_{category}"
            ),
            InlineKeyboardButton(text="🤖 AI", callback_data=f"analyze_{article['id']}"),
        ])
        kb_rows.append([
            InlineKeyboardButton(
                text=f"🔄 {t['btn_translate']} #{num}",
                callback_data=f"translate_{article['id']}"
            ),
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=f"◀️ {t['btn_prev']}", callback_data=f"cat_{category}_{page-1}"))
    if start + NEWS_PER_PAGE < total:
        nav.append(InlineKeyboardButton(text=f"{t['btn_next']} ▶️", callback_data=f"cat_{category}_{page+1}"))
    if nav:
        kb_rows.append(nav)
    kb_rows.append([InlineKeyboardButton(text=t["btn_back"], callback_data="news_menu")])

    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    try:
        await cb.message.edit_text(cards_text[:4096], reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Edit failed: {e}")
        await bot.send_message(cb.from_user.id, cards_text[:4096], reply_markup=kb, parse_mode="HTML")

# ── Read Full ──────────────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("read_"))
async def read_full(cb: CallbackQuery):
    parts      = cb.data.split("_", 3)
    article_id = parts[1]
    page       = int(parts[2]) if len(parts) > 2 else 0
    category   = parts[3] if len(parts) > 3 else "politics"
    lang       = db.get_user(cb.from_user.id)["lang"]
    t          = get_text(lang)
    article    = db.get_article(article_id)

    if not article:
        await cb.answer(t["article_not_found"], show_alert=True)
        return

    content = article.get("full") or article.get("summary", "")
    text = (
        f"📄 <b>{esc(article['title'])}</b>\n"
        f"<i>🏛 {esc(article.get('source',''))}  •  🕐 {article.get('published','')}</i>\n\n"
        f"{'─'*28}\n\n{esc(content[:3500])}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🤖 {t['btn_ai_analyze']}", callback_data=f"analyze_{article_id}"),
            InlineKeyboardButton(text=f"🔄 {t['btn_translate']}",  callback_data=f"translate_{article_id}"),
        ],
        [InlineKeyboardButton(text=t["btn_back"], callback_data=f"cat_{category}_{page}")],
    ])
    try:
        await cb.message.edit_text(text[:4096], reply_markup=kb, parse_mode="HTML")
    except Exception:
        await bot.send_message(cb.from_user.id, text[:4096], reply_markup=kb, parse_mode="HTML")

# ── Translate ──────────────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("translate_"))
async def translate_article(cb: CallbackQuery):
    article_id = cb.data.replace("translate_", "")
    lang       = db.get_user(cb.from_user.id)["lang"]
    t          = get_text(lang)
    article    = db.get_article(article_id)
    if not article:
        await cb.answer(t["article_not_found"], show_alert=True)
        return
    await cb.answer()
    msg = await bot.send_message(cb.from_user.id, f"🔄 <b>{t['translating']}...</b>", parse_mode="HTML")
    target = "узбекский язык (латиница)" if lang == "uz" else "русский язык"
    prompt = (
        f"Переведи на {target}. Только перевод без пояснений.\n\n"
        f"Заголовок: {article['title']}\n\nТекст: {article.get('summary', '')}"
    )
    result =  call_ai(prompt)
    kb = back_kb(lang)
    await msg.edit_text(
        f"🔄 <b>{t['translation_result']}</b>\n<i>🏛 {esc(article.get('source',''))}</i>\n\n{'─'*28}\n\n{esc(result[:3800])}",
        reply_markup=kb, parse_mode="HTML"
    )

# ── AI Analyze ────────────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("analyze_"))
async def analyze_article(cb: CallbackQuery):
    article_id = cb.data.replace("analyze_", "")
    lang       = db.get_user(cb.from_user.id)["lang"]
    t          = get_text(lang)
    article    = db.get_article(article_id)
    if not article:
        await cb.answer(t["article_not_found"], show_alert=True)
        return
    await cb.answer()
    msg = await bot.send_message(cb.from_user.id, f"🤖 <b>{t['ai_analyzing']}...</b>", parse_mode="HTML")
    lang_instr = "Отвечай на русском языке." if lang == "ru" else "O'zbek tilida javob ber."
    prompt = (
        f"Проанализируй новость:\n\nЗаголовок: {article['title']}\n"
        f"Содержание: {article.get('summary', '')}\n\n{lang_instr}\n\n"
        f"Структура:\n📊 Суть события — 2-3 предложения\n"
        f"🌍 Геополитическое влияние\n💰 Экономические последствия\n"
        f"🔮 Прогноз развития\n⚖️ Оценка достоверности"
    )
    full_prompt = (
    "Ты — опытный политический и экономический аналитик. "
    "Объективен, без предвзятости.\n\n" + prompt
)

    result = call_ai(full_prompt)
    kb = back_kb(lang)
    await msg.edit_text(
        f"🤖 <b>AI Анализ</b>\n{'─'*28}\n\n{esc(result[:4000])}",
        reply_markup=kb, parse_mode="HTML"
    )

# ── AI Chat ───────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "ai_chat")
async def start_ai_chat(cb: CallbackQuery, state: FSMContext):
    lang = db.get_user(cb.from_user.id)["lang"]
    t    = get_text(lang)
    await state.set_state(ChatState.chatting)
    await state.update_data(history=[])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_stop_chat"], callback_data="main_menu")]
    ])
    await cb.message.edit_text(t["ai_chat_start"], reply_markup=kb, parse_mode="HTML")

@dp.message(ChatState.chatting)
async def ai_chat_message(message: Message, state: FSMContext):
    lang = db.get_user(message.from_user.id)["lang"]
    t = get_text(lang)
    data = await state.get_data()
    history = data.get("history", [])

    history.append({"role": "user", "content": message.text})
    if len(history) > 20:
        history = history[-20:]

    thinking = await message.answer(f"🤔 <i>{t['ai_thinking']}...</i>", parse_mode="HTML")

    lang_instr = "Отвечай на русском языке." if lang == "ru" else "O'zbek tilida javob ber."
    system = f"Ты — эксперт по мировой политике и экономике. {lang_instr} Структурируй ответы с эмодзи."

    try:
        full_prompt = system + "\n\n"

        for msg in history:
            full_prompt += f"{msg['role']}: {msg['content']}\n"

        reply = call_ai(full_prompt)

        history.append({"role": "assistant", "content": reply})
        await state.update_data(history=history)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_stop_chat"], callback_data="main_menu")]
        ])

        await thinking.edit_text(
            esc(reply)[:4096],
            reply_markup=kb,
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"AI chat error: {e}")
        await thinking.edit_text(f"⚠️ {t['ai_error']}")

# ── Digest ────────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "digest")
async def daily_digest(cb: CallbackQuery):
    lang = db.get_user(cb.from_user.id)["lang"]
    t    = get_text(lang)
    await cb.message.edit_text(f"⏳ <b>{t['digest_loading']}</b>", parse_mode="HTML")
    all_articles = []
    for cat in ["politics", "economy", "world"]:
        arts = await fetch_news(cat)
        all_articles.extend(arts[:3])
    save_articles(all_articles)
    headlines = "\n".join([f"- {a['title']}" for a in all_articles[:10]])
    lang_instr = "Отвечай на русском языке." if lang == "ru" else "O'zbek tilida javob ber."
    prompt = (
        f"Составь дайджест главных мировых новостей:\n\n{headlines}\n\n{lang_instr}\n\n"
        f"Формат:\n🌍 ДАЙДЖЕСТ ДНЯ\n\n📌 [3-4 события по 2-3 предложения]\n\n"
        f"📊 Общая картина: [абзац]\n\n⭐ Главный вывод: [одно предложение]"
    )
    digest =  call_ai(prompt)
    date_str = datetime.now().strftime("%d.%m.%Y")
    await cb.message.edit_text(
        f"📅 <b>{date_str}</b>\n\n{esc(digest)}",
        reply_markup=back_kb(lang), parse_mode="HTML"
    )

# ── Trends ────────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "trends")
async def show_trends(cb: CallbackQuery):
    lang = db.get_user(cb.from_user.id)["lang"]
    t    = get_text(lang)
    await cb.message.edit_text(f"⏳ <b>{t['trends_loading']}</b>", parse_mode="HTML")
    articles = []
    for cat in ["politics", "economy", "world", "asia", "europe"]:
        arts = await fetch_news(cat)
        articles.extend(arts[:2])
    save_articles(articles)
    headlines = "\n".join([f"- {a['title']}" for a in articles[:12]])
    lang_instr = "Отвечай на русском языке." if lang == "ru" else "O'zbek tilida javob ber."
    prompt = (
        f"На основе заголовков определи тренды:\n\n{headlines}\n\n{lang_instr}\n\n"
        f"🔥 ТОП-3 горячих темы (с объяснением)\n📈 Экономические тренды\n"
        f"🌐 Геополитические тренды\n🔭 На что обратить внимание"
    )
    result =  call_ai(prompt)
    await cb.message.edit_text(esc(result)[:4096], reply_markup=back_kb(lang), parse_mode="HTML")

# ── Quiz ──────────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "quiz")
async def start_quiz(cb: CallbackQuery):
    lang = db.get_user(cb.from_user.id)["lang"]
    t    = get_text(lang)
    await cb.message.edit_text(f"⏳ <b>{t['quiz_loading']}</b>", parse_mode="HTML")
    lang_instr = "На русском языке." if lang == "ru" else "O'zbek tilida."
    prompt = (
        f"Придумай вопрос-викторину по мировой политике/экономике. {lang_instr}\n\n"
        f"СТРОГИЙ ФОРМАТ (ничего лишнего):\n"
        f"ВОПРОС: [вопрос]\n"
        f"A) [вариант]\nB) [вариант]\nC) [вариант]\nD) [вариант]\n"
        f"ОТВЕТ: [только буква]\nПОЯСНЕНИЕ: [2-3 предложения]"
    )
    raw   =  call_ai(prompt)
    lines = raw.strip().split("\n")
    question = ""; options = []; answer = ""; explanation = ""
    for line in lines:
        line = line.strip()
        if line.startswith("ВОПРОС:") or line.startswith("SAVOL:"):
            question = line.split(":", 1)[1].strip()
        elif line[:2] in ("A)", "B)", "C)", "D)"):
            options.append(line)
        elif line.startswith("ОТВЕТ:") or line.startswith("JAVOB:"):
            answer = line.split(":", 1)[1].strip()
        elif line.startswith("ПОЯСНЕНИЕ:") or line.startswith("IZOH:"):
            explanation = line.split(":", 1)[1].strip()

    if not question or not options:
        await cb.message.edit_text(t["quiz_error"], reply_markup=back_kb(lang), parse_mode="HTML")
        return

    opts_text = "\n".join(options)
    ans_data  = f"{answer}||{esc(explanation)}"
    text = f"🧠 <b>{t['quiz_title']}</b>\n\n{'─'*28}\n\n❓ {esc(question)}\n\n{esc(opts_text)}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="A", callback_data=f"quiz_ans_A||{ans_data}"),
            InlineKeyboardButton(text="B", callback_data=f"quiz_ans_B||{ans_data}"),
        ],
        [
            InlineKeyboardButton(text="C", callback_data=f"quiz_ans_C||{ans_data}"),
            InlineKeyboardButton(text="D", callback_data=f"quiz_ans_D||{ans_data}"),
        ],
        [InlineKeyboardButton(text=t["btn_back"], callback_data="main_menu")],
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("quiz_ans_"))
async def quiz_answer(cb: CallbackQuery):
    lang  = db.get_user(cb.from_user.id)["lang"]
    t     = get_text(lang)
    raw   = cb.data.replace("quiz_ans_", "")
    parts = raw.split("||", 2)
    chosen      = parts[0]
    correct     = parts[1] if len(parts) > 1 else "?"
    explanation = parts[2] if len(parts) > 2 else ""
    if chosen == correct:
        result_emoji = "✅"; result_text = t["quiz_correct"]
    else:
        result_emoji = "❌"; result_text = t["quiz_wrong"].replace("{ans}", correct)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_new_quiz"], callback_data="quiz")],
        [InlineKeyboardButton(text=t["btn_back"],     callback_data="main_menu")],
    ])
    await cb.message.edit_text(
        f"{result_emoji} <b>{result_text}</b>\n\n💡 {esc(explanation)}",
        reply_markup=kb, parse_mode="HTML"
    )

# ── Search ────────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "search")
async def start_search(cb: CallbackQuery, state: FSMContext):
    lang = db.get_user(cb.from_user.id)["lang"]
    t    = get_text(lang)
    await state.set_state(SearchState.waiting_query)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_back"], callback_data="main_menu")]
    ])
    await cb.message.edit_text(t["search_prompt"], reply_markup=kb, parse_mode="HTML")

@dp.message(SearchState.waiting_query)
async def do_search(message: Message, state: FSMContext):
    lang  = db.get_user(message.from_user.id)["lang"]
    t     = get_text(lang)
    query = message.text.strip()
    await state.clear()
    thinking = await message.answer(f"🔍 <i>{t['searching']}...</i>", parse_mode="HTML")
    lang_instr = "Отвечай на русском языке." if lang == "ru" else "O'zbek tilida javob ber."
    prompt = (
        f'Пользователь ищет: "{query}"\n\n{lang_instr}\n\n'
        f"Дай экспертный ответ в контексте мировой политики и экономики:\n"
        f"📌 Суть темы\n🌍 Текущее положение\n🔑 Ключевые игроки\n📈 Последние тенденции"
    )
    result =  call_ai(prompt)
    await thinking.edit_text(
        f"🔍 <b>{esc(query)}</b>\n{'─'*28}\n\n{esc(result[:4000])}",
        reply_markup=back_kb(lang), parse_mode="HTML"
    )

# ── Settings ──────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "settings")
async def settings(cb: CallbackQuery):
    lang = db.get_user(cb.from_user.id)["lang"]
    t    = get_text(lang)
    user = db.get_user(cb.from_user.id)
    cur_lang = "🇷🇺 Русский" if lang == "ru" else "🇺🇿 O'zbek"
    text = (
        f"⚙️ <b>{t['settings_title']}</b>\n\n"
        f"👤 {t['settings_name']}: <b>{esc(cb.from_user.full_name)}</b>\n"
        f"🌐 {t['settings_lang']}: <b>{cur_lang}</b>\n"
        f"📅 {t['settings_joined']}: <b>{user.get('joined','')[:10]}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_change_lang"], callback_data="change_lang")],
        [InlineKeyboardButton(text=t["btn_back"],        callback_data="main_menu")],
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "change_lang")
async def change_lang(cb: CallbackQuery):
    await cb.message.edit_text(
        "🌍 <b>Выберите язык / Tilni tanlang:</b>",
        reply_markup=lang_kb(), parse_mode="HTML"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    u    = db.get_user(message.from_user.id)
    lang = u["lang"] if u else "ru"
    t    = get_text(lang)
    await message.answer(t["help_text"], reply_markup=main_menu(lang), parse_mode="HTML")

# ── Main ──────────────────────────────────────────────────────────────────────
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню / Bosh menyu"),
        BotCommand(command="help",  description="Помощь / Yordam"),
    ])

async def main():
    await set_commands()
    logger.info("🤖 PolNews AI Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())