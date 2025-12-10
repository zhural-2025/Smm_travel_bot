"""
Основной модуль Telegram-бота для SMM-эксперта по путешествиям
"""
import sys
import io
# Устанавливаем UTF-8 кодировку для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.enums import ParseMode
from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable

from config import config
from models import (
    init_db, add_post, get_unpublished_posts, 
    mark_post_published, get_active_schedule, Schedule, SessionLocal,
    fix_null_is_published, get_posts_diagnostic
)
from generators import (
    generate_complete_post, download_image,
    generate_content_recommendations, generate_topic_ideas, analyze_post_idea
)
from scheduler import (
    setup_scheduler, start_scheduler, stop_scheduler, 
    add_default_schedule, publish_post_to_telegram
)

# Настройка логирования
import os
from pathlib import Path

# Создаем директорию для логов
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Настройка логирования в файл и консоль
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()


# Middleware для логирования всех сообщений
class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user = event.from_user
        logger.info(
            f"📨 Сообщение от {user.id} (@{user.username or 'N/A'}) "
            f"в чате {event.chat.id}: {event.text or '[медиа/стикер/другое]'}"
        )
        return await handler(event, data)

# Регистрируем middleware
dp.message.middleware(LoggingMiddleware())


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id == config.ADMIN_ID


# ======================== ОБРАБОТЧИКИ КОМАНД ========================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для использования этого бота.")
        return
    
    welcome_text = """
🌍 <b>Добро пожаловать в SMM-бота для блога о путешествиях!</b>

Этот бот поможет вам автоматизировать создание и публикацию контента о путешествиях.

<b>📋 Доступные команды:</b>

🎨 <b>Генерация контента:</b>
/generate - Сгенерировать новый пост
/generate_custom [тема] - Сгенерировать пост на конкретную тему

📤 <b>Публикация:</b>
/publish - Опубликовать последний неопубликованный пост
/publish_now - Сгенерировать и сразу опубликовать новый пост

💡 <b>Рекомендации по контенту:</b>
/recommend - Получить полные рекомендации по контенту (темы, вовлечение, тренды)
/analyze [тема] - Анализ конкретной идеи для поста

📅 <b>Расписание:</b>
/schedule_status - Показать текущее расписание
/schedule_daily [HH:MM] - Установить ежедневную публикацию
/schedule_weekly [HH:MM] [дни] - Установить еженедельную публикацию
/schedule_start - Запустить планировщик
/schedule_stop - Остановить планировщик

📊 <b>Управление:</b>
/list_posts - Список неопубликованных постов
/all_posts - Список всех постов
/view_post [ID] - Просмотр полного текста поста
/stats - Статистика работы бота
/db_diagnostic - Диагностика базы данных
/fix_published_posts - Исправить неправильно помеченные посты

/help - Показать эту справку

Начните с команды /recommend для получения рекомендаций! ✨
"""
    await message.answer(welcome_text, parse_mode=ParseMode.HTML)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для использования этого бота.")
        return
    
    await cmd_start(message)


@dp.message(Command("generate"))
async def cmd_generate(message: Message):
    """Обработчик команды /generate - генерация нового поста"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для использования этой команды.")
        return
    
    status_msg = await message.answer("🔄 Генерирую пост... Это может занять до минуты.")
    
    try:
        # Генерируем пост
        post_data = generate_complete_post()
        
        # Сохраняем в БД (явно указываем is_published=False)
        post = add_post(
            topic=post_data['topic'],
            content=post_data['content'],
            image_url=post_data['image_url'],
            image_prompt=post_data['image_prompt'],
            is_published=False  # Явно указываем False для неопубликованных постов
        )
        logger.info(f"📝 Пост сохранен: ID={post.id}, is_published={post.is_published}")
        
        await status_msg.edit_text(f"✅ Пост сгенерирован и сохранен (ID: {post.id})\n\n"
                                  f"<b>Тема:</b> {post_data['topic']}\n\n"
                                  f"Используйте /publish для публикации.",
                                  parse_mode=ParseMode.HTML)
        
        # Показываем превью поста
        preview_text = f"📝 <b>Превью поста:</b>\n\n{post_data['content'][:500]}"
        if len(post_data['content']) > 500:
            preview_text += "..."
        
        await message.answer(preview_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Ошибка генерации поста: {e}")
        await status_msg.edit_text(f"❌ Ошибка при генерации поста: {str(e)}")


@dp.message(Command("generate_custom"))
async def cmd_generate_custom(message: Message):
    """Обработчик команды /generate_custom - генерация поста на заданную тему"""
    if not is_admin(message.from_user.id):
        return
    
    # Извлекаем тему из команды
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Укажите тему поста.\n\n"
                           "Пример: /generate_custom Лучшие пляжи Бали")
        return
    
    topic = parts[1]
    status_msg = await message.answer(f"🔄 Генерирую пост на тему: <b>{topic}</b>",
                                     parse_mode=ParseMode.HTML)
    
    try:
        # Генерируем пост с заданной темой
        post_data = generate_complete_post(topic=topic)
        
        # Сохраняем в БД (явно указываем is_published=False)
        post = add_post(
            topic=topic,
            content=post_data['content'],
            image_url=post_data['image_url'],
            image_prompt=post_data['image_prompt'],
            is_published=False  # Явно указываем False для неопубликованных постов
        )
        
        await status_msg.edit_text(f"✅ Пост сгенерирован (ID: {post.id})")
        
        # Показываем превью
        preview_text = f"📝 <b>Превью:</b>\n\n{post_data['content'][:500]}"
        if len(post_data['content']) > 500:
            preview_text += "..."
        
        await message.answer(preview_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Ошибка генерации поста: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")


# ======================== РЕКОМЕНДАЦИИ ПО КОНТЕНТУ ========================

@dp.message(Command("recommend"))
async def cmd_recommend(message: Message):
    """Обработчик команды /recommend - получить рекомендации по контенту"""
    if not is_admin(message.from_user.id):
        return
    
    status_msg = await message.answer("💡 Генерирую рекомендации по контенту...")
    
    try:
        result = generate_content_recommendations()
        
        if result['success']:
            header = f"📊 <b>РЕКОМЕНДАЦИИ ПО КОНТЕНТУ</b>\n"
            header += f"📅 Сезон: {result['season']} | Месяц: {result['month']}\n\n"
            
            await status_msg.edit_text(header + result['recommendations'], 
                                       parse_mode=ParseMode.HTML)
        else:
            await status_msg.edit_text(f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")
            
    except Exception as e:
        logger.error(f"Ошибка получения рекомендаций: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")


@dp.message(Command("analyze"))
async def cmd_analyze(message: Message):
    """Обработчик команды /analyze - анализ идеи для поста"""
    if not is_admin(message.from_user.id):
        return
    
    # Извлекаем тему из команды
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "❌ Укажите идею для анализа.\n\n"
            "Пример: /analyze Топ-10 мест для фотосессий в Париже"
        )
        return
    
    idea = parts[1]
    status_msg = await message.answer(f"🔍 Анализирую идею: <b>{idea}</b>",
                                     parse_mode=ParseMode.HTML)
    
    try:
        result = analyze_post_idea(idea)
        
        if result['success']:
            header = f"📊 <b>АНАЛИЗ ИДЕИ</b>\n"
            header += f"💡 Тема: {result['idea']}\n\n"
            
            text = header + result['analysis']
            text += "\n\n<i>💡 Используйте /generate_custom для создания поста на эту тему</i>"
            
            await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
        else:
            await status_msg.edit_text(f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")
            
    except Exception as e:
        logger.error(f"Ошибка анализа идеи: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")


@dp.message(Command("publish"))
async def cmd_publish(message: Message):
    """Обработчик команды /publish - публикация неопубликованного поста"""
    if not is_admin(message.from_user.id):
        return
    
    # Получаем неопубликованные посты (отсортированные по дате, последние сначала)
    unpublished = get_unpublished_posts()
    
    if not unpublished:
        await message.answer("❌ Нет неопубликованных постов.\n\n"
                           "Используйте /generate для создания нового поста.")
        return
    
    # Берем последний созданный пост (первый в отсортированном списке)
    post = unpublished[0]
    logger.info(f"Публикую пост ID: {post.id}, тема: {post.topic}, создан: {post.created_at}")
    logger.info(f"Изображение в БД: {'Есть' if post.image_url else 'Нет'}")
    
    status_msg = await message.answer(f"📤 Публикую пост ID: {post.id}...\n"
                                     f"📝 Тема: {post.topic}\n"
                                     f"🖼️ Изображение: {'✅' if post.image_url else '❌'}")
    
    try:
        post_data = {
            'content': post.content,
            'image_url': post.image_url if post.image_url else None
        }
        
        logger.info(f"Данные для публикации: content_length={len(post_data['content'])}, image_url={post_data['image_url']}")
        message_id = await publish_post_to_telegram(bot, post_data)
        
        if message_id:
            mark_post_published(post.id, message_id)
            await status_msg.edit_text(f"✅ Пост успешно опубликован!\n\n"
                                      f"ID поста: {post.id}\n"
                                      f"ID сообщения: {message_id}")
        else:
            await status_msg.edit_text("❌ Ошибка при публикации поста")
            
    except Exception as e:
        logger.error(f"Ошибка публикации: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")


@dp.message(Command("publish_now"))
async def cmd_publish_now(message: Message):
    """Обработчик команды /publish_now - генерация и немедленная публикация"""
    if not is_admin(message.from_user.id):
        return
    
    status_msg = await message.answer("🔄 Генерирую и публикую пост...")
    
    try:
        # Генерируем пост
        post_data = generate_complete_post()
        
        # Сохраняем в БД
        post = add_post(
            topic=post_data['topic'],
            content=post_data['content'],
            image_url=post_data['image_url'],
            image_prompt=post_data['image_prompt']
        )
        
        # Публикуем
        message_id = await publish_post_to_telegram(bot, post_data)
        
        if message_id:
            mark_post_published(post.id, message_id)
            await status_msg.edit_text(f"✅ Пост сгенерирован и опубликован!\n\n"
                                      f"<b>Тема:</b> {post_data['topic']}\n"
                                      f"ID поста: {post.id}",
                                      parse_mode=ParseMode.HTML)
        else:
            await status_msg.edit_text("❌ Пост сгенерирован, но не удалось опубликовать")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")


@dp.message(Command("schedule_status"))
async def cmd_schedule_status(message: Message):
    """Показать текущее расписание"""
    if not is_admin(message.from_user.id):
        return
    
    schedule = get_active_schedule()
    
    if not schedule:
        await message.answer("📅 Активное расписание не настроено.\n\n"
                           "Используйте /schedule_daily или /schedule_weekly для настройки.")
        return
    
    status_text = f"""
📅 <b>Текущее расписание публикаций:</b>

⏰ Частота: {schedule.frequency}
🕐 Время: {schedule.time}
"""
    
    if schedule.days_of_week:
        days_map = {
            '0': 'Понедельник', '1': 'Вторник', '2': 'Среда', '3': 'Четверг',
            '4': 'Пятница', '5': 'Суббота', '6': 'Воскресенье'
        }
        days = [days_map.get(d, d) for d in schedule.days_of_week.split(',')]
        status_text += f"📆 Дни недели: {', '.join(days)}\n"
    
    status_text += f"""
✅ Активно: {'Да' if schedule.is_active else 'Нет'}
🕒 Последний запуск: {schedule.last_run.strftime('%Y-%m-%d %H:%M') if schedule.last_run else 'Еще не было'}
"""
    
    await message.answer(status_text, parse_mode=ParseMode.HTML)


@dp.message(Command("schedule_daily"))
async def cmd_schedule_daily(message: Message):
    """Установить ежедневную публикацию"""
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Укажите время в формате HH:MM\n\n"
                           "Пример: /schedule_daily 10:00")
        return
    
    time_str = parts[1]
    
    # Проверка формата времени
    try:
        hour, minute = map(int, time_str.split(':'))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
    except:
        await message.answer("❌ Неверный формат времени. Используйте HH:MM (например, 10:00)")
        return
    
    # Обновляем расписание в БД
    db = SessionLocal()
    try:
        schedule = db.query(Schedule).filter(Schedule.is_active == True).first()
        
        if schedule:
            schedule.frequency = 'daily'
            schedule.time = time_str
            schedule.days_of_week = None
        else:
            schedule = Schedule(frequency='daily', time=time_str, is_active=True)
            db.add(schedule)
        
        db.commit()
        
        # Перенастраиваем планировщик
        setup_scheduler(bot)
        
        await message.answer(f"✅ Расписание обновлено!\n\n"
                           f"Посты будут публиковаться ежедневно в {time_str}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка обновления расписания: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        db.close()


@dp.message(Command("schedule_weekly"))
async def cmd_schedule_weekly(message: Message):
    """Установить еженедельную публикацию"""
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ Укажите время и дни недели\n\n"
                           "Пример: /schedule_weekly 10:00 0,2,4\n"
                           "где 0=ПН, 1=ВТ, 2=СР, 3=ЧТ, 4=ПТ, 5=СБ, 6=ВС")
        return
    
    time_str = parts[1]
    days_str = parts[2]
    
    # Обновляем расписание
    db = SessionLocal()
    try:
        schedule = db.query(Schedule).filter(Schedule.is_active == True).first()
        
        if schedule:
            schedule.frequency = 'weekly'
            schedule.time = time_str
            schedule.days_of_week = days_str
        else:
            schedule = Schedule(
                frequency='weekly',
                time=time_str,
                days_of_week=days_str,
                is_active=True
            )
            db.add(schedule)
        
        db.commit()
        
        # Перенастраиваем планировщик
        setup_scheduler(bot)
        
        await message.answer(f"✅ Расписание обновлено!\n\n"
                           f"Посты будут публиковаться по расписанию: {time_str}, дни: {days_str}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        db.close()


@dp.message(Command("chatid"))
async def cmd_chatid(message: Message):
    """Получить ID текущего чата - для настройки группы"""
    chat_id = message.chat.id
    chat_type = message.chat.type
    chat_title = message.chat.title or "Личный чат"
    user_id = message.from_user.id
    
    text = f"""
📋 <b>Информация о чате:</b>

🆔 <b>Chat ID:</b> <code>{chat_id}</code>
👤 <b>Ваш User ID:</b> <code>{user_id}</code>
📝 <b>Название:</b> {chat_title}
📂 <b>Тип:</b> {chat_type}

<b>Текущий ID группы в настройках:</b> <code>{config.TELEGRAM_GROUP_ID}</code>
<b>Текущий ADMIN_ID в настройках:</b> <code>{config.ADMIN_ID}</code>

{'✅ Ваш ID совпадает с ADMIN_ID!' if user_id == config.ADMIN_ID else '❌ Ваш ID НЕ совпадает с ADMIN_ID! Обновите ADMIN_ID в файле .env'}
{'✅ ID группы совпадает!' if str(chat_id) == str(config.TELEGRAM_GROUP_ID) else '❌ ID группы НЕ совпадает! Обновите TELEGRAM_GROUP_ID в файле .env'}
"""
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("schedule_start"))
async def cmd_schedule_start(message: Message):
    """Запустить планировщик"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        start_scheduler()
        await message.answer("✅ Планировщик запущен!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


@dp.message(Command("schedule_stop"))
async def cmd_schedule_stop(message: Message):
    """Остановить планировщик"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        stop_scheduler()
        await message.answer("⏸️ Планировщик остановлен")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


@dp.message(Command("list_posts"))
async def cmd_list_posts(message: Message):
    """Показать список неопубликованных постов"""
    if not is_admin(message.from_user.id):
        return
    
    from models import Post
    db = SessionLocal()
    
    try:
        # Сначала исправляем NULL значения
        fixed = fix_null_is_published()
        if fixed > 0:
            logger.info(f"✅ Исправлено {fixed} NULL значений при запросе списка постов")
        
        # Получаем диагностику
        diag = get_posts_diagnostic()
        
        # Получаем неопубликованные посты
        unpublished = get_unpublished_posts()
        
        # Получаем все посты для справки
        total = db.query(Post).count()
        
        if not unpublished:
            # Показываем детальную информацию если нет неопубликованных
            text = f"""📭 <b>Нет неопубликованных постов</b>

📊 <b>Статистика БД:</b>
• Всего постов: {total}
• Опубликовано: {diag['published_true']}
• Не опубликовано: {diag['published_false']}
• Со значением NULL: {diag['published_null']}

{"✅ Исправлено NULL записей: " + str(fixed) if fixed > 0 else ""}

💡 Используйте /generate для создания нового поста
💡 Используйте /db_diagnostic для детальной диагностики"""
            
            await message.answer(text, parse_mode=ParseMode.HTML)
            return
        
        text = f"📝 <b>Неопубликованные посты ({len(unpublished)}):</b>\n\n"
        
        for post in unpublished[:10]:  # Показываем первые 10
            status_info = ""
            if post.is_published is None:
                status_info = " (было NULL, исправлено)"
            
            text += f"📌 <b>ID: {post.id}</b>{status_info}\n"
            text += f"🏷️ Тема: {post.topic}\n"
            text += f"📅 Создан: {post.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            text += f"🖼️ Изображение: {'✅' if post.image_url else '❌'}\n"
            text += f"👁️ Просмотр: /view_post_{post.id}\n\n"
        
        if len(unpublished) > 10:
            text += f"\n... и еще {len(unpublished) - 10} постов\n"
        
        text += "\n💡 Используйте /view_post_[ID] для просмотра полного текста поста"
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Ошибка получения списка постов: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        db.close()


@dp.message(Command("all_posts"))
async def cmd_all_posts(message: Message):
    """Показать все посты (краткий список)"""
    if not is_admin(message.from_user.id):
        return
    
    from models import Post
    db = SessionLocal()
    
    try:
        all_posts = db.query(Post).order_by(Post.created_at.desc()).limit(20).all()
        
        if not all_posts:
            await message.answer("📭 В базе данных нет постов")
            return
        
        text = f"📝 <b>Все посты (показано {len(all_posts)} из последних):</b>\n\n"
        
        for post in all_posts:
            status = "✅ Опубликован" if post.is_published else "⏳ Не опубликован"
            text += f"📌 <b>ID: {post.id}</b> - {status}\n"
            text += f"🏷️ {post.topic}\n"
            text += f"📅 {post.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            text += f"👁️ /view_post_{post.id}\n\n"
        
        text += "\n💡 Используйте /view_post_[ID] для просмотра полного текста поста"
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        
    finally:
        db.close()


@dp.message(Command("view_post"))
async def cmd_view_post(message: Message):
    """Просмотр конкретного поста по ID"""
    if not is_admin(message.from_user.id):
        return
    
    # Извлекаем ID из команды
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "❌ Укажите ID поста.\n\n"
            "Пример: /view_post 5\n\n"
            "Или используйте /list_posts для списка постов"
        )
        return
    
    try:
        post_id = int(parts[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом. Пример: /view_post 5")
        return
    
    from models import Post
    db = SessionLocal()
    
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        
        if not post:
            await message.answer(f"❌ Пост с ID {post_id} не найден")
            return
        
        # Формируем информацию о посте
        status = "✅ Опубликован" if post.is_published else "⏳ Не опубликован"
        if post.published_at:
            status += f" ({post.published_at.strftime('%Y-%m-%d %H:%M')})"
        
        text = f"📌 <b>ПОСТ ID: {post.id}</b>\n"
        text += f"📅 Создан: {post.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        text += f"🏷️ Тема: {post.topic}\n"
        text += f"📊 Статус: {status}\n"
        if post.telegram_message_id:
            text += f"💬 Telegram ID: {post.telegram_message_id}\n"
        text += f"🖼️ Изображение: {'✅' if post.image_url else '❌'}\n\n"
        text += f"📝 <b>ТЕКСТ ПОСТА:</b>\n\n"
        text += f"{post.content}\n"
        
        # Telegram ограничение - 4096 символов
        if len(text) > 4000:
            # Разбиваем на части
            part1 = text[:4000]
            await message.answer(part1, parse_mode=ParseMode.HTML)
            await message.answer(text[4000:], parse_mode=ParseMode.HTML)
        else:
            await message.answer(text, parse_mode=ParseMode.HTML)
        
    finally:
        db.close()


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    """Показать статистику"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для использования этой команды.")
        return
    
    from models import Post
    db = SessionLocal()
    
    try:
        total_posts = db.query(Post).count()
        from sqlalchemy import or_
        published_posts = db.query(Post).filter(Post.is_published.is_(True)).count()
        # Учитываем как False, так и NULL значения для неопубликованных постов
        unpublished_posts = db.query(Post).filter(
            or_(
                Post.is_published.is_(False),
                Post.is_published.is_(None)
            )
        ).count()
        
        text = f"""
📊 <b>Статистика бота:</b>

📝 Всего постов: {total_posts}
✅ Опубликовано: {published_posts}
⏳ Ожидают публикации: {unpublished_posts}

🤖 Бот работает с {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        
    finally:
        db.close()


@dp.message(Command("db_diagnostic"))
async def cmd_db_diagnostic(message: Message):
    """Диагностика базы данных постов"""
    if not is_admin(message.from_user.id):
        return
    
    from models import Post
    db = SessionLocal()
    
    try:
        # Получаем диагностику
        diag = get_posts_diagnostic()
        
        # Исправляем NULL значения
        fixed = fix_null_is_published()
        
        # Получаем все посты для детальной информации
        all_posts = db.query(Post).order_by(Post.created_at.desc()).limit(10).all()
        
        text = f"""🔍 <b>Диагностика базы данных:</b>

📊 <b>Статистика:</b>
• Всего постов: {diag['total']}
• is_published = True: {diag['published_true']}
• is_published = False: {diag['published_false']}
• is_published = NULL: {diag['published_null']}

{"✅ Исправлено NULL записей: " + str(fixed) if fixed > 0 else "✅ NULL записей не обнаружено"}

📝 <b>Последние 10 постов:</b>
"""
        
        for post in all_posts:
            status_icon = "✅" if post.is_published else ("❓" if post.is_published is None else "⏳")
            status_text = "Опубликован" if post.is_published else ("NULL" if post.is_published is None else "Не опубликован")
            text += f"\n{status_icon} ID {post.id}: {post.topic[:30]}... ({status_text})"
        
        text += "\n\n💡 Используйте /list_posts для списка неопубликованных"
        text += "\n💡 Используйте /fix_published_posts для исправления недавних постов"
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Ошибка диагностики БД: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        db.close()


@dp.message(Command("fix_published_posts"))
async def cmd_fix_published_posts(message: Message):
    """Исправить посты, которые были созданы через /generate, но помечены как опубликованные"""
    if not is_admin(message.from_user.id):
        return
    
    from models import Post
    from datetime import datetime, timedelta
    db = SessionLocal()
    
    try:
        # Находим посты, которые были созданы недавно (за последние 24 часа)
        # и помечены как опубликованные, но не имеют telegram_message_id
        # Это обычно означает, что они были созданы через /generate, но неправильно помечены
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        # Ищем опубликованные посты без telegram_message_id, созданные недавно
        posts_to_fix = db.query(Post).filter(
            Post.is_published.is_(True),
            Post.telegram_message_id.is_(None),
            Post.created_at >= yesterday
        ).all()
        
        if not posts_to_fix:
            await message.answer("✅ Нет постов для исправления.\n\n"
                               "Все недавние посты либо неопубликованы, либо имеют ID сообщения Telegram.")
            return
        
        fixed_count = 0
        for post in posts_to_fix:
            post.is_published = False
            post.published_at = None
            fixed_count += 1
        
        if fixed_count > 0:
            db.commit()
            await message.answer(f"✅ Исправлено {fixed_count} постов!\n\n"
                               f"Посты ID: {', '.join([str(p.id) for p in posts_to_fix])}\n"
                               f"были помечены как неопубликованные.\n\n"
                               f"Теперь используйте /list_posts для проверки.")
        else:
            await message.answer("❌ Не удалось исправить посты")
            
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка исправления постов: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        db.close()


# ======================== ОБРАБОТЧИК КНОПОК ПРОСМОТРА ПОСТОВ ========================

@dp.message(F.text.regexp(r'^/view_post_\d+$'))
async def cmd_view_post_button(message: Message):
    """Обработчик кнопок /view_post_[ID]"""
    if not is_admin(message.from_user.id):
        return
    
    # Извлекаем ID из команды
    try:
        post_id = int(message.text.split('_')[-1])
    except ValueError:
        await message.answer("❌ Неверный формат команды")
        return
    
    from models import Post
    db = SessionLocal()
    
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        
        if not post:
            await message.answer(f"❌ Пост с ID {post_id} не найден")
            return
        
        # Формируем информацию о посте
        status = "✅ Опубликован" if post.is_published else "⏳ Не опубликован"
        if post.published_at:
            status += f" ({post.published_at.strftime('%Y-%m-%d %H:%M')})"
        
        text = f"📌 <b>ПОСТ ID: {post.id}</b>\n"
        text += f"📅 Создан: {post.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        text += f"🏷️ Тема: {post.topic}\n"
        text += f"📊 Статус: {status}\n"
        if post.telegram_message_id:
            text += f"💬 Telegram ID: {post.telegram_message_id}\n"
        text += f"🖼️ Изображение: {'✅' if post.image_url else '❌'}\n\n"
        text += f"📝 <b>ТЕКСТ ПОСТА:</b>\n\n"
        text += f"{post.content}\n"
        
        # Telegram ограничение - 4096 символов
        if len(text) > 4000:
            # Разбиваем на части
            part1 = text[:4000]
            await message.answer(part1, parse_mode=ParseMode.HTML)
            await message.answer(text[4000:], parse_mode=ParseMode.HTML)
        else:
            await message.answer(text, parse_mode=ParseMode.HTML)
        
    finally:
        db.close()


# ======================== ОБРАБОТЧИК НЕИЗВЕСТНЫХ КОМАНД ========================

@dp.message()
async def handle_unknown_message(message: Message):
    """Обработчик всех неизвестных сообщений и команд"""
    logger.info(f"Получено сообщение от {message.from_user.id} (@{message.from_user.username}): {message.text}")
    
    # Если это команда, но не распознана
    if message.text and message.text.startswith('/'):
        if not is_admin(message.from_user.id):
            await message.answer(
                "❌ У вас нет прав для использования этого бота.\n\n"
                "Если вы администратор, проверьте, что ваш ID совпадает с ADMIN_ID в настройках.\n\n"
                "Используйте команду /chatid для проверки вашего ID."
            )
        else:
            await message.answer(
                "❓ Неизвестная команда.\n\n"
                "Используйте /help для просмотра доступных команд."
            )
    # Если это обычное сообщение
    elif message.text:
        if not is_admin(message.from_user.id):
            await message.answer(
                "👋 Привет! Я бот для автоматизации SMM-контента о путешествиях.\n\n"
                "❌ У вас нет прав для использования этого бота.\n\n"
                "Если вы администратор, проверьте настройки ADMIN_ID.\n"
                "Используйте /start для начала работы."
            )
        else:
            await message.answer(
                "💬 Я понимаю только команды.\n\n"
                "Используйте /help для просмотра доступных команд."
            )


# ======================== ОСНОВНАЯ ФУНКЦИЯ ========================

async def main():
    """Главная функция запуска бота"""
    logger.info("🚀 Запуск SMM-бота для путешествий...")
    
    try:
        # Проверяем конфигурацию
        config.validate()
        logger.info("✅ Конфигурация проверена")
        logger.info(f"   - ADMIN_ID: {config.ADMIN_ID}")
        logger.info(f"   - GROUP_ID: {config.TELEGRAM_GROUP_ID}")
        
        # Инициализируем базу данных
        init_db()
        logger.info("✅ База данных инициализирована")
        
        # Добавляем расписание по умолчанию, если его нет
        add_default_schedule()
        
        # Настраиваем планировщик
        setup_scheduler(bot)
        start_scheduler()
        logger.info("✅ Планировщик запущен")
        
        # Проверяем и удаляем webhook если активен (polling не работает с webhook)
        try:
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url:
                logger.warning(f"⚠️ Найден активный webhook: {webhook_info.url}")
                logger.info("🔄 Удаляю webhook для использования polling...")
                await bot.delete_webhook(drop_pending_updates=True)
                logger.info("✅ Webhook удален")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при проверке webhook: {e}")
        
        # Проверяем подключение к боту
        try:
            me = await bot.get_me()
            logger.info(f"✅ Бот подключен: @{me.username} ({me.first_name})")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Telegram: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # Запускаем бота в режиме polling
        logger.info("✅ Бот готов к работе! Ожидание сообщений...")
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
        
    except KeyboardInterrupt:
        logger.info("⏸️ Остановка бота...")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("🛑 Завершение работы бота...")
        stop_scheduler()
        try:
            await bot.session.close()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())

