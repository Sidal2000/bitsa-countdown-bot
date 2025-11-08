import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime, timedelta
import pytz

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройки мероприятия
EVENT_NAME = "5 вёрст Битца"
EVENT_TIME = "09:00"
EVENT_DAY = 5  # 5 = суббота (0 = понедельник, 6 = воскресенье)
TIMEZONE = pytz.timezone('Europe/Moscow')

# Хранилище данных
bot_data = {
    'next_event': None,  # Дата следующего мероприятия
    'is_custom': False,  # Флаг: перенесено ли мероприятие
    'message_id': None,  # ID сообщения с отсчетом
    'chat_id': None,  # ID чата
    'event_started': False  # Флаг: началось ли мероприятие
}

def get_next_saturday_9am():
    """Получить следующую субботу в 9:00"""
    now = datetime.now(TIMEZONE)
    days_ahead = EVENT_DAY - now.weekday()
    
    if days_ahead <= 0:  # Если сегодня суббота или позже
        days_ahead += 7
    
    next_saturday = now + timedelta(days=days_ahead)
    next_event = next_saturday.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # Если сегодня суббота, но еще не 9:00
    if now.weekday() == EVENT_DAY and now.hour < 9:
        next_event = now.replace(hour=9, minute=0, second=0, microsecond=0)
    
    return next_event

def format_time_left(time_left):
    """Форматирование оставшегося времени"""
    days = time_left.days
    hours, remainder = divmod(time_left.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return f"{days} дней, {hours} часов, {minutes} минут"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приветственное сообщение и запуск отсчета"""
    chat_id = update.effective_chat.id
    
    # Если отсчет еще не запущен, инициализируем
    if bot_data['next_event'] is None:
        bot_data['next_event'] = get_next_saturday_9am()
        bot_data['is_custom'] = False
    
    bot_data['chat_id'] = chat_id
    
    await update.message.reply_text(
        f'🏃‍♂️ Бот обратного отсчета для "{EVENT_NAME}" запущен!\n\n'
        f'📅 Мероприятие проводится каждую субботу в 9:00\n\n'
        f'Доступные команды:\n'
        f'/start - Запустить бота\n'
        f'/status - Показать текущий статус\n'
        f'/reschedule ГГГГ-ММ-ДД ЧЧ:ММ - Перенести на другую дату\n'
        f'/cancel - Отменить ближайшее мероприятие\n'
        f'/reset - Вернуться к обычному расписанию'
    )
    
    # Запуск отсчета
    message = await update.message.reply_text('Инициализация отсчета...')
    bot_data['message_id'] = message.message_id
    
    # Остановка предыдущих задач
    current_jobs = context.job_queue.get_jobs_by_name('countdown_update')
    for job in current_jobs:
        job.schedule_removal()
    
    # Запуск периодического обновления (каждые 60 секунд)
    context.job_queue.run_repeating(
        update_countdown,
        interval=60,
        first=1,
        name='countdown_update'
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать текущий статус"""
    if bot_data['next_event'] is None:
        await update.message.reply_text('Отсчет не запущен. Используйте /start')
        return
    
    next_event = bot_data['next_event']
    is_custom = bot_data['is_custom']
    
    status_text = (
        f'📊 Текущий статус:\n\n'
        f'📅 Следующее мероприятие: {next_event.strftime("%d.%m.%Y %H:%M")}\n'
        f'🔄 Тип: {"Перенесено" if is_custom else "По расписанию (суббота 9:00)"}\n'
    )
    
    await update.message.reply_text(status_text)

async def reschedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Перенести мероприятие на другую дату"""
    if len(context.args) < 2:
        await update.message.reply_text(
            'Неверный формат!\n'
            'Используйте: /reschedule ГГГГ-ММ-ДД ЧЧ:ММ\n'
            'Пример: /reschedule 2025-11-10 09:00'
        )
        return
    
    try:
        date_str = context.args[0]
        time_str = context.args[1]
        
        new_datetime = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')
        new_datetime = TIMEZONE.localize(new_datetime)
        
        now = datetime.now(TIMEZONE)
        if new_datetime <= now:
            await update.message.reply_text('Дата и время должны быть в будущем!')
            return
        
        bot_data['next_event'] = new_datetime
        bot_data['is_custom'] = True
        bot_data['event_started'] = False
        
        await update.message.reply_text(
            f'✅ Мероприятие перенесено на {new_datetime.strftime("%d.%m.%Y %H:%M")}\n'
            f'После этого мероприятия расписание вернется к обычному (суббота 9:00)'
        )
        
    except ValueError:
        await update.message.reply_text(
            'Неверный формат даты или времени!\n'
            'Используйте: ГГГГ-ММ-ДД ЧЧ:ММ'
        )

async def cancel_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отменить ближайшее мероприятие"""
    if bot_data['next_event'] is None:
        await update.message.reply_text('Нет запланированных мероприятий')
        return
    
    # Переносим на следующую субботу
    bot_data['next_event'] = get_next_saturday_9am()
    bot_data['is_custom'] = False
    bot_data['event_started'] = False
    
    await update.message.reply_text(
        f'❌ Ближайшее мероприятие отменено\n'
        f'📅 Следующее мероприятие: {bot_data["next_event"].strftime("%d.%m.%Y %H:%M")}'
    )

async def reset_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вернуться к обычному расписанию"""
    bot_data['next_event'] = get_next_saturday_9am()
    bot_data['is_custom'] = False
    bot_data['event_started'] = False
    
    await update.message.reply_text(
        f'🔄 Возврат к обычному расписанию\n'
        f'📅 Следующее мероприятие: {bot_data["next_event"].strftime("%d.%m.%Y %H:%M")} (суббота)'
    )

async def update_countdown(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обновление сообщения с отсчетом"""
    if bot_data['chat_id'] is None or bot_data['message_id'] is None:
        return
    
    if bot_data['next_event'] is None:
        return
    
    chat_id = bot_data['chat_id']
    message_id = bot_data['message_id']
    next_event = bot_data['next_event']
    
    now = datetime.now(TIMEZONE)
    time_left = next_event - now
    
    # Если мероприятие началось
    if time_left.total_seconds() <= 0 and not bot_data['event_started']:
        bot_data['event_started'] = True
        
        # Отправляем сообщение о старте
        start_message = (
            f'🏁🏁🏁\n\n'
            f'Дата {now.strftime("%d-%m-%Y")}, Старт 5 вёрст Битца! Набираем скорость!\n\n'
            f'🏁🏁🏁'
        )
        
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=start_message
            )
        except Exception as e:
            logger.error(f"Ошибка обновления: {e}")
        
        # Планируем переключение на следующее мероприятие через 1.5 часа
        context.job_queue.run_once(
            switch_to_next_event,
            when=90 * 60,  # 1.5 часа в секундах
            name='switch_event'
        )
        
        return
    
    # Если мероприятие уже началось, ничего не делаем (ждем 1.5 часа)
    if bot_data['event_started']:
        return
    
    # Обновляем отсчет
    countdown_text = (
        f'⏰ Обратный отсчет до {EVENT_NAME} ⏰\n\n'
        f'📅 Дата: {next_event.strftime("%d.%m.%Y %H:%M")}\n'
        f'📍 День: {next_event.strftime("%A")}\n'
        f'{"🔄 Перенесено" if bot_data["is_custom"] else "📆 По расписанию"}\n\n'
        f'⏳ Осталось:\n'
        f'🔹 {format_time_left(time_left)}'
    )
    
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=countdown_text
        )
    except Exception as e:
        logger.error(f"Ошибка обновления: {e}")

async def switch_to_next_event(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Переключение на следующее мероприятие через 1.5 часа после старта"""
    # Если было перенесено, возвращаемся к обычному расписанию
    if bot_data['is_custom']:
        bot_data['next_event'] = get_next_saturday_9am()
        bot_data['is_custom'] = False
    else:
        # Иначе просто берем следующую субботу
        bot_data['next_event'] = get_next_saturday_9am()
    
    bot_data['event_started'] = False
    
    # Отправляем новое сообщение с отсчетом
    if bot_data['chat_id']:
        try:
            message = await context.bot.send_message(
                chat_id=bot_data['chat_id'],
                text=f'📅 Отсчет до следующего мероприятия начался!\n'
                     f'Дата: {bot_data["next_event"].strftime("%d.%m.%Y %H:%M")}'
            )
            bot_data['message_id'] = message.message_id
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")

def main() -> None:
    """Запуск бота"""
    # ВСТАВЬТЕ СЮДА ВАШ ТОКЕН ОТ BOTFATHER
    TOKEN = "8373375322:AAGXnJCVdC9GjAVS63t_cMNwPL7pJZsFcwU"
    
    application = Application.builder().token(TOKEN).build()
    
    # Регистрация команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("reschedule", reschedule))
    application.add_handler(CommandHandler("cancel", cancel_event))
    application.add_handler(CommandHandler("reset", reset_schedule))
    
    # Запуск бота
    logger.info("Бот 5 вёрст Битца запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()