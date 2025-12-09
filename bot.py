# bot.py
import os
import asyncio
import logging
from typing import Optional, List, Tuple
from collections import defaultdict

# ---------------- Django bootstrap ----------------
import django
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "config.settings")
)
django.setup()

from django.db import transaction
from asgiref.sync import sync_to_async

# ---- Модели (у тебя app: eflab) ----
from eflab.models import Survey, Question, Client, Answer, Mark  # поля см. твои модели :contentReference[oaicite:1]{index=1}
from eflab.models import SurveyGift
# ---------------- Aiogram 3.7+ ----------------
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile,
)

import os.path

# ---------------- Логирование ----------------
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN in environment (BOT_TOKEN=...)")

bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# =======================================================
# ========  ПАМЯТЬ ДЛЯ МУЛЬТИВЫБОРА (в процессе)  =======
# =======================================================
# selections[user_id][question_id] = set of selected options
selections: dict[int, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))

# =======================================================
# ==============   СИНХРОННЫЕ ORM ФУНКЦИИ   =============
# =======================================================

def _get_or_create_client_sync(tg_id: int, username: str, full_name: str) -> Client:
    """
    Создаём/находим клиента по tg_id (unique); обновляем acc_tg при изменении username.
    Client: name, acc_tg, email, phone, tg_id.  :contentReference[oaicite:2]{index=2}
    """
    name = (full_name or "").strip() or username or str(tg_id)
    acc = f"@{username}" if username else str(tg_id)
    client, _ = Client.objects.get_or_create(
        tg_id=tg_id,
        defaults={"name": name[:100], "acc_tg": acc, "email": "", "phone": ""},
    )
    if client.acc_tg != acc:
        client.acc_tg = acc
        client.save(update_fields=["acc_tg"])
    return client


def _get_survey_by_slug_or_first_active_sync(slug: Optional[str]) -> Optional[Survey]:
    """
    Survey: slug, name, active, hello_text ...  :contentReference[oaicite:3]{index=3}
    """
    qs = Survey.objects.filter(active=True)
    if slug:
        s = qs.filter(slug=slug).first()
        if s:
            return s
    return qs.first()


def _list_active_surveys_sync() -> List[Tuple[str, str]]:
    """[(name, slug)] всех активных опросов."""
    return list(Survey.objects.filter(active=True).values_list("name", "slug"))


def _answered_qids_sync(client: Client, survey: Survey) -> set[int]:
    return set(
        Answer.objects.filter(client_id=client, que__survey=survey)
        .values_list("que_id", flat=True)
    )


def _next_question_sync(client: Client, survey: Survey) -> Optional[Question]:
    """
    Question: survey, numb (порядок), que_text, type_q, file, kind_file ...  :contentReference[oaicite:4]{index=4}
    """
    done = _answered_qids_sync(client, survey)
    return (
        Question.objects
        .filter(survey=survey)
        .order_by("numb")
        .exclude(id__in=done)
        .first()
    )


def _progress_text_sync(client: Client, survey: Survey) -> str:
    total = Question.objects.filter(survey=survey).count()
    done = len(_answered_qids_sync(client, survey))
    return f"Прогресс: {done}/{total}"


def _get_question_by_id_sync(qid: int) -> Optional[Question]:
    return Question.objects.select_related("survey").filter(id=qid).first()


def _get_marks_for_question_sync(q: Question) -> List[Mark]:
    """
    Mark: mark_text, que -> Question  :contentReference[oaicite:5]{index=5}
    """
    return list(Mark.objects.filter(que=q))


def _save_answer_sync(client: Client, question: Question, value: str) -> Answer:
    """
    Answer: client_tg_acc, que, ans, date(auto_now_add), client_id -> Client  :contentReference[oaicite:6]{index=6}
    """
    with transaction.atomic():
        return Answer.objects.create(
            client_tg_acc=client.acc_tg,
            que=question,
            ans=value,
            client_id=client,
        )

def _get_gift_sync(survey: Survey):
    return SurveyGift.objects.filter(survey=survey).first()

def _delete_answers_for_client_survey_sync(client: Client, survey: Survey) -> int:
    """Удалить все ответы пользователя по конкретному опросу (для ретейка)."""
    qs = Answer.objects.filter(client_id=client, que__survey=survey)
    count = qs.count()
    qs.delete()
    return count



# ===== async-обёртки над ORM =====
aget_or_create_client = sync_to_async(_get_or_create_client_sync, thread_sensitive=True)
aget_survey = sync_to_async(_get_survey_by_slug_or_first_active_sync, thread_sensitive=True)
alist_active_surveys = sync_to_async(_list_active_surveys_sync, thread_sensitive=True)
a_next_question = sync_to_async(_next_question_sync, thread_sensitive=True)
a_progress_text = sync_to_async(_progress_text_sync, thread_sensitive=True)
a_get_question = sync_to_async(_get_question_by_id_sync, thread_sensitive=True)
a_get_marks = sync_to_async(_get_marks_for_question_sync, thread_sensitive=True)
a_save_answer = sync_to_async(_save_answer_sync, thread_sensitive=True)
a_delete_answers = sync_to_async(_delete_answers_for_client_survey_sync, thread_sensitive=True)
a_get_gift = sync_to_async(_get_gift_sync, thread_sensitive=True)


# =======================================================
# ===================  КНОПКИ / UI  =====================
# =======================================================
def kb_yes_no(prefix: str, payload: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Да", callback_data=f"{prefix}:yes:{payload}"),
        InlineKeyboardButton(text="Нет", callback_data=f"{prefix}:no:{payload}"),
    ]])


def kb_multi(question_id: int, options: List[str], chosen: set[str]) -> InlineKeyboardMarkup:
    """Мультивыбор: чекбоксы + Готово/Пропустить."""
    rows = []
    for opt in options:
        checked = "✅ " if opt in chosen else "▫️ "
        rows.append([
            InlineKeyboardButton(
                text=f"{checked}{opt[:48]}",
                callback_data=f"multi:{question_id}:toggle:{opt}"
            )
        ])
    rows.append([
        InlineKeyboardButton(text="Готово", callback_data=f"multi:{question_id}:done"),
        InlineKeyboardButton(text="Пропустить", callback_data=f"multi:{question_id}:skip"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_surveys(items: List[Tuple[str, str]]) -> InlineKeyboardMarkup:
    """Клавиатура со списком активных опросов: (name, slug)."""
    rows = []
    for name, slug in items:
        rows.append([InlineKeyboardButton(text=name[:64], callback_data=f"pick:{slug}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_in_survey(slug: str, show_menu: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Начать заново", callback_data=f"restart:{slug}")],
    ]
    if show_menu:
        rows.append([InlineKeyboardButton(text="Выбрать другой опрос", callback_data="menu:surveys")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# =======================================================
# ================  ОТПРАВКА ВОПРОСА  ===================
# =======================================================
async def send_question(msg: Message, survey: Survey, q: Question):
    header = f"<b>Вопрос {q.numb}</b>\n{q.que_text or ''}".strip()

    sent = False

    if q.file:
        try:
            # Всегда используем путь до файла внутри контейнера
            if hasattr(q.file, "path") and os.path.exists(q.file.path):
                f = FSInputFile(q.file.path)

                kind = (q.kind_file or "document").lower()

                if kind == "photo":
                    await msg.answer_photo(f, caption=header)
                elif kind == "video":
                    await msg.answer_video(f, caption=header)
                elif kind == "audio":
                    await msg.answer_audio(f, caption=header)
                else:
                    await msg.answer_document(f, caption=header)

                sent = True
            else:
                print("Файл вопроса не найден на диске:", q.file)
        except Exception as e:
            print("Ошибка отправки файла вопроса:", e)

    if not sent:
        await msg.answer(header)

    # тип вопроса — кнопки / текст
    typeq = (q.type_q or "").lower()

    if typeq == "yes_or_no":
        await msg.answer("Ваш ответ:", reply_markup=kb_yes_no("ans_yn", str(q.id)))

    elif typeq == "one_of_some":
        marks = await a_get_marks(q)
        options = [m.mark_text for m in marks] if marks else []

        selections[msg.from_user.id][q.id] = selections[msg.from_user.id].get(q.id, set())

        await msg.answer(
            "Выберите варианты (можно несколько):",
            reply_markup=kb_multi(q.id, options, selections[msg.from_user.id][q.id])
        )

    else:
        await msg.answer("Напишите ответ текстом:")



async def ask_next_or_finish(msg: Message, client: Client, survey: Survey):
    """
    Отправляет следующий вопрос или подарок (если вопросы закончились).
    """
    q = await a_next_question(client, survey)

    # ---------------------------------------------------------
    # 1. ЕСЛИ ВОПРОСОВ НЕТ → ОТПРАВЛЯЕМ ПОДАРОК + ФИНАЛЬНОЕ СООБЩЕНИЕ
    # ---------------------------------------------------------
    if not q:
        gift = await a_get_gift(survey)

        if gift and gift.file:
            try:
                # путь до файла внутри контейнера
                if hasattr(gift.file, "path") and os.path.exists(gift.file.path):
                    file_path = gift.file.path
                    f = FSInputFile(file_path)

                    caption = gift.caption or "Спасибо за прохождение! Вот ваш подарок 🎁"
                    name = gift.file.name.lower()

                    # Определяем тип файла
                    if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                        await msg.answer_photo(f, caption=caption)
                    elif name.endswith((".mp4", ".mov", ".avi", ".mkv")):
                        await msg.answer_video(f, caption=caption)
                    elif name.endswith((".mp3", ".aac", ".wav", ".ogg")):
                        await msg.answer_audio(f, caption=caption)
                    else:
                        await msg.answer_document(f, caption=caption)
                else:
                    print("Файл подарка не найден в контейнере:", gift.file)

            except Exception as e:
                print("Ошибка отправки подарка:", e)

        # финальное сообщение
        items = await alist_active_surveys()
        show_menu = len(items) > 1

        await msg.answer(
            f"Готово! Вы ответили на все вопросы опроса «{survey.name}».",
            reply_markup=kb_in_survey(survey.slug, show_menu)
        )
        return

    # ---------------------------------------------------------
    # 2. ЕСЛИ ВОПРОС ЕСТЬ → ОТПРАВЛЯЕМ ПРОГРЕСС + САМ ВОПРОС
    # ---------------------------------------------------------
    progress = await a_progress_text(client, survey)
    if progress:
        await msg.answer(progress)

    await send_question(msg, survey, q)

# =======================================================
# =====================  ХЕНДЛЕРЫ  ======================
# =======================================================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    """
    /start <slug> — запускает конкретный опрос.
    /start        — если активный ровно один, начинаем его сразу; если несколько — покажем меню.
    """
    tg_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""
    client = await aget_or_create_client(tg_id, username, full_name)

    parts = (message.text or "").split(maxsplit=1)
    slug = parts[1].strip() if len(parts) == 2 else None

    if slug:
        survey = await aget_survey(slug)
        if not survey:
            await message.answer("Опрос не найден или неактивен. Нажмите /surveys для списка.")
            return
        hello = getattr(survey, "hello_text", None) or f"Привет, {client.name}! Приглашаем пройти опрос «{survey.name}»."
        await message.answer(hello)
        await ask_next_or_finish(message, client, survey)   # сразу начинаем
        return

    # без slug — смотрим список активных
    items = await alist_active_surveys()  # [(name, slug)]
    if not items:
        await message.answer("Сейчас нет активных опросов.")
        return
    if len(items) == 1:
        # автозапуск единственного активного
        only_name, only_slug = items[0]
        survey = await aget_survey(only_slug)
        hello = getattr(survey, "hello_text", None) or f"Привет, {client.name}! Приглашаем пройти опрос «{survey.name}»."
        await message.answer(hello)
        await ask_next_or_finish(message, client, survey)
        return

    # несколько — покажем меню
    await message.answer("Выберите опрос:", reply_markup=kb_surveys(items))

@dp.message(Command("surveys"))
async def cmd_surveys(message: Message):
    items = await alist_active_surveys()
    if not items:
        await message.answer("Сейчас нет активных опросов.")
        return
    if len(items) == 1:
        # сразу начать единственный активный
        _, only_slug = items[0]
        tg_id = message.from_user.id
        username = message.from_user.username or ""
        full_name = message.from_user.full_name or ""
        client = await aget_or_create_client(tg_id, username, full_name)

        survey = await aget_survey(only_slug)
        hello = getattr(survey, "hello_text", None) or f"Привет, {client.name}! Приглашаем пройти опрос «{survey.name}»."
        await message.answer(hello)
        await ask_next_or_finish(message, client, survey)
        return

    await message.answer("Выберите опрос:", reply_markup=kb_surveys(items))

@dp.callback_query(F.data == "menu:surveys")
async def cb_menu_surveys(call: CallbackQuery):
    await call.answer()
    items = await alist_active_surveys()
    if not items:
        await call.message.answer("Сейчас нет активных опросов.")
        return
    if len(items) == 1:
        # автозапуск единственного активного
        _, only_slug = items[0]
        tg_id = call.from_user.id
        username = call.from_user.username or ""
        full_name = call.from_user.full_name or ""
        client = await aget_or_create_client(tg_id, username, full_name)

        survey = await aget_survey(only_slug)
        hello = getattr(survey, "hello_text", None) or f"Привет, {client.name}! Приглашаем пройти опрос «{survey.name}»."
        await call.message.answer(hello)
        await ask_next_or_finish(call.message, client, survey)
        return

    await call.message.answer("Выберите опрос:", reply_markup=kb_surveys(items))



@dp.callback_query(F.data.startswith("pick:"))
async def cb_pick(call: CallbackQuery):
    """Выбор конкретного опроса из списка активных."""
    _, slug = call.data.split(":", 1)
    await call.answer()

    survey = await aget_survey(slug)
    if not survey:
        await call.message.answer("Опрос не найден или неактивен.")
        return

    # привет и старт
    tg_id = call.from_user.id
    username = call.from_user.username or ""
    full_name = call.from_user.full_name or ""
    client = await aget_or_create_client(tg_id, username, full_name)

    hello = getattr(survey, "hello_text", None) or f"Привет, {client.name}! Приглашаем пройти опрос «{survey.name}»."
    await call.message.answer(hello)
    await call.message.answer("Готовы пройти опрос сейчас?", reply_markup=kb_yes_no("ready", survey.slug))


@dp.callback_query(F.data.startswith("ready:"))
async def cb_ready(call: CallbackQuery):
    """Кнопка «Готовы пройти опрос?»"""
    _, yn, slug = call.data.split(":", 2)
    await call.answer()

    if yn == "no":
        await call.message.answer("Ок! Когда будете готовы — /surveys чтобы выбрать опрос, или /continue для продолжения.")
        return

    tg_id = call.from_user.id
    username = call.from_user.username or ""
    full_name = call.from_user.full_name or ""
    client = await aget_or_create_client(tg_id, username, full_name)

    survey = await aget_survey(slug)
    if not survey:
        await call.message.answer("Сейчас нет активных опросов.")
        return

    await call.message.answer(f"Отлично! Начинаем «{survey.name}».")
    await ask_next_or_finish(call.message, client, survey)


@dp.message(Command("continue"))
async def cmd_continue(message: Message):
    """
    Возобновление (можно /continue <slug>).
    Если slug не указан — предложим меню опросов.
    """
    tg_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""
    client = await aget_or_create_client(tg_id, username, full_name)

    parts = (message.text or "").split(maxsplit=1)
    slug = parts[1].strip() if len(parts) == 2 else None

    if not slug:
        items = await alist_active_surveys()
        if not items:
            await message.answer("Сейчас нет активных опросов.")
            return
        await message.answer("Выберите опрос для продолжения:", reply_markup=kb_surveys(items))
        return

    survey = await aget_survey(slug)
    if not survey:
        await message.answer("Опрос не найден или неактивен.")
        return

    await message.answer(f"Продолжаем «{survey.name}».", reply_markup=kb_in_survey(survey.slug))
    await ask_next_or_finish(message, client, survey)


@dp.message(Command("restart"))
async def cmd_restart(message: Message):
    """
    Полностью начать заново: /restart <slug>
    Удаляет прошлые ответы пользователя по опросу и стартует с вопроса №1.
    """
    tg_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""
    client = await aget_or_create_client(tg_id, username, full_name)

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Укажи слаг опроса: /restart <slug>\nИли открой меню /surveys.")
        return

    slug = parts[1].strip()
    survey = await aget_survey(slug)
    if not survey:
        await message.answer("Опрос не найден или неактивен.")
        return

    deleted = await a_delete_answers(client, survey)
    await message.answer(f"Старые ответы удалены ({deleted}). Начинаем заново «{survey.name}».")
    await ask_next_or_finish(message, client, survey)


@dp.callback_query(F.data.startswith("restart:"))
async def cb_restart(call: CallbackQuery):
    """Кнопка «Начать заново» внутри опроса."""
    _, slug = call.data.split(":", 1)
    await call.answer()

    tg_id = call.from_user.id
    username = call.from_user.username or ""
    full_name = call.from_user.full_name or ""
    client = await aget_or_create_client(tg_id, username, full_name)

    survey = await aget_survey(slug)
    if not survey:
        await call.message.answer("Опрос не найден или неактивен.")
        return

    deleted = await a_delete_answers(client, survey)
    await call.message.answer(f"Старые ответы удалены ({deleted}). Начинаем заново «{survey.name}».")
    await ask_next_or_finish(call.message, client, survey)

# ---------- Да/Нет ----------
@dp.callback_query(F.data.startswith("ans_yn:"))
async def cb_ans_yesno(call: CallbackQuery):
    _, yn, qid = call.data.split(":", 2)
    await call.answer()

    q = await a_get_question(int(qid))
    if not q:
        await call.message.answer("Вопрос не найден.")
        return

    tg_id = call.from_user.id
    username = call.from_user.username or ""
    full_name = call.from_user.full_name or ""
    client = await aget_or_create_client(tg_id, username, full_name)

    val = "Да" if yn == "yes" else "Нет"
    await a_save_answer(client, q, val)

    await call.message.answer(f"Ответ записан: <b>{val}</b>")
    await ask_next_or_finish(call.message, client, q.survey)

# ---------- Мультивыбор (one_of_some) ----------
@dp.callback_query(F.data.startswith("multi:"))
async def cb_multi(call: CallbackQuery):
    # data: multi:<qid>:(toggle|done|skip)[:<value>]
    parts = call.data.split(":", 3)
    _, qid_s, action, *rest = parts
    qid = int(qid_s)
    await call.answer()

    q = await a_get_question(qid)
    if not q:
        await call.message.answer("Вопрос не найден.")
        return

    user_id = call.from_user.id
    chosen = selections[user_id][qid]

    if action == "toggle":
        value = rest[0] if rest else ""
        if value in chosen:
            chosen.remove(value)
        else:
            chosen.add(value)
        # перерисуем клавиатуру
        marks = await a_get_marks(q)
        options = [m.mark_text for m in marks] if marks else []
        try:
            await call.message.edit_reply_markup(
                reply_markup=kb_multi(qid, options, chosen)
            )
        except Exception:
            await call.message.answer(
                "Обновлён выбор:",
                reply_markup=kb_multi(qid, options, chosen)
            )
        return

    # Сохранение/пропуск
    tg_id = call.from_user.id
    username = call.from_user.username or ""
    full_name = call.from_user.full_name or ""
    client = await aget_or_create_client(tg_id, username, full_name)

    if action == "skip":
        await a_save_answer(client, q, "")
        selections[user_id].pop(qid, None)
        await call.message.answer("Ответ записан: <i>пропуск</i>")
        await ask_next_or_finish(call.message, client, q.survey)
        return

    if action == "done":
        value = "; ".join(sorted(chosen)) if chosen else ""
        await a_save_answer(client, q, value)
        selections[user_id].pop(qid, None)
        shown = value if value else "<i>пропуск</i>"
        await call.message.answer(f"Ответ записан: {shown}")
        await ask_next_or_finish(call.message, client, q.survey)
        return

# ---------- Свободный текст как ответ ----------
@dp.message(F.text & ~F.text.startswith("/"))
async def msg_text_answer(message: Message):
    tg_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""
    client = await aget_or_create_client(tg_id, username, full_name)

    # найдём опрос, где ещё есть неотвеченные вопросы
    @sync_to_async(thread_sensitive=True)
    def _find_survey_with_pending(cli: Client) -> Optional[Survey]:
        for s in Survey.objects.filter(active=True):
            if _next_question_sync(cli, s) is not None:
                return s
        return Survey.objects.filter(active=True).first()

    survey = await _find_survey_with_pending(client)
    if not survey:
        await message.answer("Сейчас нет активных опросов.")
        return

    q = await a_next_question(client, survey)
    if q is None:
        items = await alist_active_surveys()
        show_menu = len(items) > 1
        await message.answer(
            f"По «{survey.name}» вопросы уже закончились.",
            reply_markup=kb_in_survey(survey.slug, show_menu)
        )
        return

    txt = (message.text or "").strip()
    if not txt:
        await message.answer("Пустой ответ не сохранён, повторите, пожалуйста.")
        return

    await a_save_answer(client, q, txt)
    await message.answer("Ответ записан.")
    await ask_next_or_finish(message, client, survey)

# ====================== RUN ======================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
