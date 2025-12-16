import os
import asyncio
import logging
from collections import defaultdict
from typing import Union

# ================= Django bootstrap =================
import django
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "config.settings")
)
django.setup()

from django.db import transaction
from asgiref.sync import sync_to_async

from eflab.models import Survey, Question, Client, Answer, Mark

# ================= Aiogram =================
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ================= Keyboards =================
from keyboards import (
    kb_start,
    kb_surveys,
    kb_yes_no,
    kb_one_of_many,
    kb_multi,
    kb_finish,
)

# ================= Config =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

logging.basicConfig(level=logging.INFO)

bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

Target = Union[Message, CallbackQuery]

# ====================================================
# ================= STATE ============================
# ====================================================
last_bot_message: dict[int, int] = {}
multi_select = defaultdict(lambda: defaultdict(set))

# ====================================================
# ================= ORM SAFE =========================
# ====================================================
@sync_to_async(thread_sensitive=True)
def get_survey_by_question(question_id: int) -> Survey:
    return (
        Survey.objects
        .filter(question__id=question_id)
        .distinct()
        .first()
    )

@sync_to_async(thread_sensitive=True)
def get_client(tg_id: int, username: str, full_name: str) -> Client:
    name = full_name or username or str(tg_id)
    acc = f"@{username}" if username else str(tg_id)

    client, _ = Client.objects.get_or_create(
        tg_id=tg_id,
        defaults=dict(name=name[:100], acc_tg=acc)
    )
    return client


@sync_to_async(thread_sensitive=True)
def get_active_surveys():
    return list(Survey.objects.filter(active=True).values_list("name", "slug"))


@sync_to_async(thread_sensitive=True)
def get_survey(slug: str):
    return Survey.objects.filter(slug=slug, active=True).first()


@sync_to_async(thread_sensitive=True)
def get_next_question(client: Client, survey: Survey):
    answered = Answer.objects.filter(
        client_id=client,
        que__survey=survey
    ).values_list("que_id", flat=True)

    return (
        Question.objects
        .filter(survey=survey)
        .exclude(id__in=answered)
        .order_by("numb")
        .first()
    )


@sync_to_async(thread_sensitive=True)
def get_progress(client: Client, survey: Survey):
    total = Question.objects.filter(survey=survey).count()
    done = Answer.objects.filter(client_id=client, que__survey=survey).count()
    return f"<b>Вопрос {done + 1} из {total}</b>\n{'⬤' * done}{'◯' * (total - done)}"


@sync_to_async(thread_sensitive=True)
def get_marks(question: Question):
    return list(Mark.objects.filter(que=question).values_list("mark_text", flat=True))


@sync_to_async(thread_sensitive=True)
def save_answer(client: Client, question: Question, value: str):
    with transaction.atomic():
        Answer.objects.create(
            client_id=client,
            que=question,
            ans=value,
            client_tg_acc=client.acc_tg
        )


@sync_to_async(thread_sensitive=True)
def reset_survey(client: Client, survey: Survey):
    Answer.objects.filter(client_id=client, que__survey=survey).delete()


# ====================================================
# ================= UTIL =============================
# ====================================================
def chat_and_user(target: Target):
    if isinstance(target, CallbackQuery):
        return target.message.chat.id, target.from_user.id
    return target.chat.id, target.from_user.id


async def send_clean(target: Target, text: str, reply_markup=None):
    chat_id, user_id = chat_and_user(target)

    old_message_id = last_bot_message.get(user_id)

    if old_message_id:
        # 1️⃣ Сначала УБИРАЕМ КНОПКИ
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=old_message_id,
                reply_markup=None
            )
        except:
            pass

        # 2️⃣ Потом пробуем УДАЛИТЬ сообщение
        try:
            await bot.delete_message(
                chat_id=chat_id,
                message_id=old_message_id
            )
        except:
            pass

    # 3️⃣ Отправляем новое сообщение
    msg = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup
    )

    last_bot_message[user_id] = msg.message_id
    return msg


# ====================================================
# ================= FLOW =============================
# ====================================================
async def show_start(target: Target):
    surveys = await get_active_surveys()
    await send_clean(target, "Добро пожаловать 👋", kb_start(surveys))


async def ask_next(target: Target, client: Client, survey: Survey):
    q = await get_next_question(client, survey)

    if not q:
        await send_clean(
            target,
            "Вы завершили опрос 🎉",
            kb_finish(survey.slug)
        )
        return

    progress = await get_progress(client, survey)
    text = f"{progress}\n\n{q.que_text}"

    if q.type_q == "yes_or_no":
        await send_clean(target, text, kb_yes_no(q.id))

    elif q.type_q == "on_of_many":
        await send_clean(target, text, kb_one_of_many(q.id, await get_marks(q)))

    elif q.type_q == "one_of_some":
        await send_clean(
            target,
            text,
            kb_multi(q.id, await get_marks(q), multi_select[target.from_user.id][q.id])
        )

    else:
        await send_clean(target, text + "\n\n<i>Введите ответ текстом</i>")


# ====================================================
# ================= HANDLERS =========================
# ====================================================
@dp.message(F.text == "/start")
async def start(message: Message):
    await show_start(message)


@dp.callback_query(F.data == "menu")
async def menu(call: CallbackQuery):
    await send_clean(call, "Выберите опрос:", kb_surveys(await get_active_surveys()))


@dp.callback_query(F.data.startswith("pick:"))
async def pick(call: CallbackQuery):
    survey = await get_survey(call.data.split(":")[1])
    client = await get_client(call.from_user.id, "", "")
    await ask_next(call, client, survey)


@dp.callback_query(F.data.startswith("restart:"))
async def restart(call: CallbackQuery):
    survey = await get_survey(call.data.split(":")[1])
    client = await get_client(call.from_user.id, "", "")
    await reset_survey(client, survey)
    multi_select.pop(call.from_user.id, None)
    await ask_next(call, client, survey)


@dp.callback_query(F.data.startswith("yn:"))
async def yes_no(call: CallbackQuery):
    _, qid, val = call.data.split(":")
    question = await sync_to_async(Question.objects.get)(id=int(qid))
    client = await get_client(call.from_user.id, "", "")

    await save_answer(client, question, "Да" if val == "yes" else "Нет")

    survey = await get_survey_by_question(question.id)
    await ask_next(call, client, survey)


@dp.callback_query(F.data.startswith("one:"))
async def one_of_many(call: CallbackQuery):
    _, qid, value = call.data.split(":", 2)
    question = await sync_to_async(Question.objects.get)(id=int(qid))
    client = await get_client(call.from_user.id, "", "")

    await save_answer(client, question, value)

    survey = await get_survey_by_question(question.id)
    await ask_next(call, client, survey)



@dp.callback_query(F.data.startswith("multi:"))
async def multi_toggle(call: CallbackQuery):
    _, qid, value = call.data.split(":", 2)
    multi_select[call.from_user.id][int(qid)].symmetric_difference_update({value})

    question = await sync_to_async(Question.objects.get)(id=int(qid))
    client = await get_client(call.from_user.id, "", "")

    survey = await get_survey_by_question(question.id)


    await send_clean(
        call,
        f"{await get_progress(client, survey)}\n\n{question.que_text}",
        kb_multi(
            question.id,
            await get_marks(question),
            multi_select[call.from_user.id][question.id]
        )
    )


@dp.callback_query(F.data.startswith("multi_done:"))
async def multi_done(call: CallbackQuery):
    qid = int(call.data.split(":")[1])
    question = await sync_to_async(Question.objects.get)(id=qid)
    client = await get_client(call.from_user.id, "", "")

    value = "; ".join(multi_select[call.from_user.id].pop(qid, []))
    await save_answer(client, question, value)

    survey = await get_survey_by_question(question.id)
    await ask_next(call, client, survey)


@dp.message(F.text)
async def text_answer(message: Message):
    client = await get_client(message.from_user.id, "", "")
    surveys = await get_active_surveys()

    for _, slug in surveys:
        survey = await get_survey(slug)
        q = await get_next_question(client, survey)
        if q:
            await save_answer(client, q, message.text)
            await ask_next(message, client, survey)
            return


# ====================================================
# ================= RUN ==============================
# ====================================================
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
