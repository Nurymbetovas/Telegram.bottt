import logging
from telegram import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, Update
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext,
    ChatJoinRequestHandler  # Добавляем этот импорт
)
from telegram.error import BadRequest
from telegram.constants import ChatMemberStatus
import sqlite3

# Конфигурация
TOKEN = '7646042819:AAHtreDM-z6Ffrndi7vWjVE0J7x_w-RGymc'  # Замените на ваш токен
GROUP_ID = -1002370108034  # Замените на ID вашей группы
ADMIN_ID = 802344099  # Замените на ваш ID

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация базы данных
def init_db():
    """Создает базу данных и таблицу для списка ожидания."""
    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS waiting_list (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            position INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

async def check_membership(user_id, context):
    """Проверяет, является ли пользователь участником группы."""
    try:
        member = await context.bot.get_chat_member(GROUP_ID, user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except BadRequest:
        return False

async def check_banned_in_group(user_id, context):
    """Проверяет, находится ли пользователь в черном списке группы (заблокирован)."""
    try:
        member = await context.bot.get_chat_member(GROUP_ID, user_id)
        return member.status == ChatMemberStatus.BANNED
    except BadRequest:
        return False

async def start(update: Update, context: CallbackContext):
    """Обрабатывает команду /start."""
    logger.info("Функция start вызвана")  # Логирование
    if update.message.chat.type != 'private':
        return

    user_id = update.message.from_user.id

    keyboard = [
        [KeyboardButton("Сілтеме"), KeyboardButton("Кіре алмадым")],
        [KeyboardButton("Aнон")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Сәлем! Топқа 100 адам ғана кіре алады. Кіру үшін Сілтеме батырмасын бас.",  # Новый текст
        reply_markup=reply_markup
    )

async def get_group_members_count(context: CallbackContext):
    """Получает количество участников группы."""
    try:
        members_count = await context.bot.get_chat_member_count(GROUP_ID)
        return members_count
    except BadRequest as e:
        logger.error(f"Ошибка при получении количества участников группы: {e}")
        return 0

async def handle_siltheme(update: Update, context: CallbackContext):
    """Обрабатывает нажатие кнопки "Сілтеме"."""
    logger.info(f"Кнопка 'Сілтеме' нажата. Текст: {update.message.text}")  # Логирование
    user_id = update.message.from_user.id
    username = update.message.from_user.username or update.message.from_user.first_name

    # Проверяем, является ли пользователь участником группы
    is_member = await check_membership(user_id, context)
    logger.info(f"Пользователь {user_id} в группе: {is_member}")  # Логирование
    if is_member:
        await update.message.reply_text("Сіз топта барсыз🥰")
    else:
        # Проверяем количество участников группы
        members_count = await get_group_members_count(context)
        logger.info(f"Количество участников группы: {members_count}")  # Логирование
        if members_count >= 100:
            # Если группа заполнена, добавляем пользователя в список ожидания
            conn = sqlite3.connect('queue.db')
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM waiting_list')
            position = cursor.fetchone()[0] + 1  # Позиция в очереди
            cursor.execute('''
                INSERT INTO waiting_list (user_id, username, position)
                VALUES (?, ?, ?)
            ''', (user_id, username, position))
            conn.commit()
            conn.close()
            await update.message.reply_text(
                f"Қазір топта бос орын жоқ, бірақ біз сізді Күту тізіміне енгіздік. Сіз қазір {position}-орындасыз. Сіздің кезегіңіз келгенде хабар береміз."
            )
        else:
            # Если есть свободные места, предлагаем присоединиться
            await update.message.reply_text(
                "Біздің топқа 100 адам ғана қосыла алады. Топқа қосылу үшін төмендегі батырманы басыңыз.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Қосылу", url="https://t.me/+UKfP2S6RKJw1YTMy")]
                ])
            )

async def handle_queue(update: Update, context: CallbackContext):
    """Обрабатывает команду 'Кезек'."""
    user_id = update.message.from_user.id
    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()
    cursor.execute('SELECT position FROM waiting_list WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        await update.message.reply_text(f"Сіз қазір {result[0]}-орында тұрсыз. Орын босағанда сізге хабарлама жібереміз.")
    else:
        await update.message.reply_text("Сіз кезекте емессіз.")

async def edit_message_and_remove_button(context: CallbackContext, user_id: int, message_id: int):
    """Изменяет сообщение и удаляет кнопку."""
    try:
        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="Сіздің уақытыңыз аяқталды, кезегіңіз сізден кейінгі адамға берілді."
        )
    except Exception as e:
        logger.error(f"Ошибка при изменении сообщения: {e}")

async def notify_first_in_queue(context: CallbackContext):
    """Уведомляет первого пользователя в очереди."""
    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username FROM waiting_list ORDER BY position LIMIT 1')
    result = cursor.fetchone()
    if result:
        user_id, username = result
        try:
            # Отправляем сообщение с кнопкой
            message = await context.bot.send_message(
                user_id,
                "🎉 Орын босады. Сіздің 1 сағат уақытыңыз бар. 1 сағат ішінде кірмесеңіз, кезегіңіз келесі адамға беріледі.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Қосылу", url="https://t.me/+UKfP2S6RKJw1YTMy")]
                ])
            )
            # Устанавливаем таймер на 1 час
            context.job_queue.run_once(
                remove_from_queue, 
                3600, 
                user_id=user_id, 
                message_id=message.message_id
            )
        except Exception as e:
            logger.error(f"Ошибка при уведомлении пользователя {user_id}: {e}")

async def remove_from_queue(context: CallbackContext):
    """Удаляет пользователя из очереди и изменяет сообщение."""
    user_id = context.job.user_id
    message_id = context.job.message_id

    # Удаляем пользователя из очереди
    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM waiting_list WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

    # Изменяем сообщение и удаляем кнопку
    await edit_message_and_remove_button(context, user_id, message_id)

    # Уведомляем пользователя
    try:
        await context.bot.send_message(
            user_id,
            "Сіздің уақытыңыз аяқталды, кезегіңіз сізден кейінгі адамға берілді."
        )
    except Exception as e:
        logger.error(f"Ошибка при уведомлении пользователя {user_id}: {e}")

async def handle_anon(update: Update, context: CallbackContext):
    """Обрабатывает нажатие кнопки "Aнон"."""
    user_id = update.message.from_user.id

    # Проверяем, является ли пользователь участником группы
    is_member = await check_membership(user_id, context)
    if is_member:
        keyboard = [[KeyboardButton("Артқа")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Осы жерге анонимді хабарлама қалдыңсаң болады. Атың, юзер ештеңе көрінбейді, тек хабарлама топқа боттың атынан барады.",
            reply_markup=reply_markup
        )
        context.user_data["anon_mode"] = True  # Включаем режим анонимного сообщения
    else:
        # Если пользователь не в группе, предлагаем присоединиться и проверить
        keyboard = [
            [InlineKeyboardButton("Топқа кіріңіз", url="https://t.me/+UKfP2S6RKJw1YTMy")],
            [InlineKeyboardButton("Тексеру", callback_data="check_membership")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Анонимді хабарламаны топта бар адам ғана жаза алады. Топқа кіріп, 'Тексеру' батырмасын басыңыз.",
            reply_markup=reply_markup
        )
        context.user_data["waiting_for_check"] = True  # Ожидаем проверки

async def handle_back(update: Update, context: CallbackContext):
    """Обрабатывает нажатие кнопки "Артқа"."""
    user_id = update.message.from_user.id

    # Возвращаем пользователя в главное меню
    keyboard = [
        [KeyboardButton("Сілтеме"), KeyboardButton("Кіре алмадым")],
        [KeyboardButton("Aнон")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Сіз негізгі мәзірге қайттыңыз.",
        reply_markup=reply_markup
    )
    context.user_data.clear()  # Очищаем данные пользователя

async def handle_anon_message(update: Update, context: CallbackContext):
    """Обрабатывает анонимные сообщения."""
    if update.message.chat.type != 'private':
        return

    user_id = update.message.from_user.id

    # Проверяем, включен ли режим анонимного сообщения
    if not context.user_data.get("anon_mode", False):
        return

    sent_message = None

    # Пересылка различных типов медиа
    if update.message.text:
        sent_message = await context.bot.send_message(GROUP_ID, f"🔹 *Анонимді хабарлама:*\n{update.message.text}", parse_mode="Markdown")
    elif update.message.voice:
        sent_message = await context.bot.send_voice(GROUP_ID, update.message.voice.file_id, caption="🔹 *Анонимді голосовое:*", parse_mode="Markdown")
    elif update.message.photo:
        sent_message = await context.bot.send_photo(GROUP_ID, update.message.photo[-1].file_id, caption="🔹 *Анонимді фото:*", parse_mode="Markdown")
    elif update.message.video:
        sent_message = await context.bot.send_video(GROUP_ID, update.message.video.file_id, caption="🔹 *Анонимді видео:*", parse_mode="Markdown")
    elif update.message.document:
        sent_message = await context.bot.send_document(GROUP_ID, update.message.document.file_id, caption="🔹 *Анонимді құжат:*", parse_mode="Markdown")
    elif update.message.animation:
        sent_message = await context.bot.send_animation(GROUP_ID, update.message.animation.file_id, caption="🔹 *Анонимді анимация:*", parse_mode="Markdown")
    elif update.message.sticker:
        sent_message = await context.bot.send_sticker(GROUP_ID, update.message.sticker.file_id)
    elif update.message.video_note:
        sent_message = await context.bot.send_video_note(GROUP_ID, update.message.video_note.file_id)
    else:
        await update.message.reply_text("Бұл типтегі хабарламаны өңдеу мүмкін емес.")
        return

    if sent_message:
        group_message_link = f"https://t.me/c/{str(GROUP_ID)[4:]}/{sent_message.message_id}"
        sender_link = f"[Жіберуші](tg://openmessage?user_id={user_id})"

        admin_text = f"🔔 *Жаңа анонимді хабарлама:*\n{update.message.text if update.message.text else '📎 Медиа файл'}\n\n{sender_link}\n[Хабарлама сілтемесі]({group_message_link})"

        await context.bot.send_message(ADMIN_ID, text=admin_text, parse_mode="Markdown")
        await update.message.reply_text("Сіз тағы анонимді хабарлама жаза аласыз немесе 'Артқа' батырмасын басып негізгі мәзірге оралыңыз.")

async def handle_cannot_join(update: Update, context: CallbackContext):
    """Обрабатывает нажатие кнопки "Кіре алмадым"."""
    user_id = update.message.from_user.id

    # Проверяем, находится ли пользователь в черном списке группы
    is_banned = await check_banned_in_group(user_id, context)
    if is_banned:
        keyboard = [[InlineKeyboardButton("Шығу", callback_data=f"request_unban_{user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Сіз қара тізімде тұрғандықтан сілтеме арқылы кіре алмай жатырсыз. Қара тізімнен шыққыңыз келеді ме?",
            reply_markup=reply_markup
        )
    else:
        # Если пользователь не заблокирован, предлагаем присоединиться
        keyboard = [[InlineKeyboardButton("Кіріңіз", url="https://t.me/+UKfP2S6RKJw1YTMy")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Сіз қара тізімде жоқсыз, сілтеме арқылы кіріңіз.",
            reply_markup=reply_markup
        )

async def handle_exit_request(update: Update, context: CallbackContext):
    """Обрабатывает запрос пользователя на выход из черного списка."""
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие кнопки

    user_id = int(query.data.split("_")[-1])  # Получаем ID пользователя

    # Отправляем пользователю подтверждение, что запрос отправлен
    await query.edit_message_text("Сіздің өтінішіңіз жіберілді. Жауап күтіңіз.")

    # Получаем данные о пользователе
    user = await context.bot.get_chat(user_id)
    user_name = user.first_name or "Пайдаланушы"
    user_username = f"@{user.username}" if user.username else "юзернейм жоқ"

    # Используем HTML-разметку
    user_link = f'<a href="tg://user?id={user_id}">{user_name}</a>'

    # Кнопки для админа
    keyboard = [
        [InlineKeyboardButton("Қабылдау", callback_data=f"accept_unban_{user_id}")],
        [InlineKeyboardButton("Қабылдамау", callback_data=f"deny_unban_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем админу запрос с HTML-разметкой
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"🔔 {user_link} ({user_username}) қара тізімнен шығуға өтініш жіберді.",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Қате ADMIN_ID-ге хабарлама жіберуде: {e}")

async def handle_admin_decision(update: Update, context: CallbackContext):
    """Обрабатывает решение администратора по запросу на разблокировку."""
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие кнопки

    action, user_id = query.data.rsplit("_", 1)
    user_id = int(user_id)

    # Получаем данные о пользователе
    user = await context.bot.get_chat(user_id)
    user_name = user.first_name or "Пайдаланушы"
    user_username = f"@{user.username}" if user.username else "юзернейм жоқ"

    # Используем HTML-разметку
    user_link = f'<a href="tg://user?id={user_id}">{user_name}</a>'

    if action == "accept_unban":
        # Разблокируем пользователя в группе
        await context.bot.unban_chat_member(GROUP_ID, user_id)
        # Отправляем сообщение пользователю
        await context.bot.send_message(
            user_id,
            "Сіздің өтінішіңіз қабылданды, сілтеме арқылы кіре аласыз.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Кіріңіз", url="https://t.me/+UKfP2S6RKJw1YTMy")]])
        )
        # Отправляем сообщение администратору
        await context.bot.send_message(
            ADMIN_ID,
            f"{user_link} қара тізімнен алынды.",
            parse_mode="HTML"
        )
    elif action == "deny_unban":
        # Отправляем сообщение пользователю
        await context.bot.send_message(user_id, "Сіздің өтінішіңіз қабылданбады.")
        # Отправляем сообщение администратору
        await context.bot.send_message(
            ADMIN_ID,
            f"{user_link} қара тізімнен алынбады.",
            parse_mode="HTML"
        )

    # Убираем кнопки, оставляя сообщение без изменений
    await query.edit_message_reply_markup(reply_markup=None)

async def handle_check_membership(update: Update, context: CallbackContext):
    """Обрабатывает нажатие кнопки "Тексеру"."""
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие кнопки

    user_id = query.from_user.id

    # Проверяем, является ли пользователь участником группы
    is_member = await check_membership(user_id, context)
    if is_member:
        await query.edit_message_text("Сіз топтасыз! Анонимді хабарлама жаза аласыз.")
    else:
        await query.edit_message_text("Сіз әлі топта емессіз. Топқа кіріңіз.")

from telegram import Update
from telegram.ext import Application, ChatJoinRequestHandler

async def handle_chat_join_request(update: Update, context: CallbackContext):
    """Обрабатывает заявки на вступление в группу."""
    user_id = update.chat_join_request.from_user.id
    chat_id = update.chat_join_request.chat.id

    # Автоматически принимаем заявку
    try:
        await context.bot.approve_chat_join_request(chat_id, user_id)
        logger.info(f"Заявка от пользователя {user_id} принята.")
    except Exception as e:
        logger.error(f"Ошибка при принятии заявки от пользователя {user_id}: {e}")

def main():
    """Запуск бота."""
    application = Application.builder().token(TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Сілтеме$"), handle_siltheme))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)^кезек$"), handle_queue))  # Команда "Кезек"
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Кіре алмадым$"), handle_cannot_join))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Aнон$"), handle_anon))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Артқа$"), handle_back))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_anon_message))
    application.add_handler(CallbackQueryHandler(handle_exit_request, pattern="^request_unban_"))
    application.add_handler(CallbackQueryHandler(handle_admin_decision, pattern="^(accept_unban|deny_unban)_"))
    application.add_handler(CallbackQueryHandler(handle_check_membership, pattern="^check_membership$"))

    # Добавляем обработчик заявок на вступление в группу
    application.add_handler(ChatJoinRequestHandler(handle_chat_join_request))

    # Периодическая проверка очереди
    job_queue = application.job_queue
    job_queue.run_repeating(notify_first_in_queue, interval=60.0, first=0.0)  # Проверка каждые 60 секунд

    # Запуск бота
    application.run_polling()

if __name__ == "__main__":
    main()
