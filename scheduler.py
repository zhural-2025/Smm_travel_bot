"""
Планировщик для автоматической публикации постов
"""
from datetime import datetime, time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from aiogram.types import FSInputFile
import asyncio
import logging

from config import config
from models import get_active_schedule, update_schedule_last_run, get_unpublished_posts, mark_post_published, add_post
from generators import generate_complete_post, download_image

# Настройка логирования
logger = logging.getLogger(__name__)

# Создаем глобальный планировщик
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


async def publish_post_to_telegram(bot: Bot, post_data: dict) -> int:
    """
    Публикация поста в Telegram группу
    
    Args:
        bot: Экземпляр Telegram бота
        post_data: Данные поста (content, image_url)
        
    Returns:
        int: ID отправленного сообщения или None
    """
    try:
        # Получаем и нормализуем group_id
        group_id_raw = config.TELEGRAM_GROUP_ID
        if not group_id_raw:
            logger.error("❌ TELEGRAM_GROUP_ID не установлен в конфигурации!")
            raise ValueError("TELEGRAM_GROUP_ID не установлен")
        
        # Преобразуем group_id в правильный формат
        # Может быть строкой (для супергрупп) или числом
        if isinstance(group_id_raw, str):
            # Пытаемся преобразовать в int, если это число
            try:
                group_id = int(group_id_raw)
            except ValueError:
                # Если не число, оставляем как строку (для супергрупп)
                group_id = group_id_raw
        else:
            group_id = group_id_raw
        
        content = post_data['content']
        
        logger.info(f"📤 Публикую пост в группу {group_id}")
        logger.info(f"📝 Длина текста: {len(content)} символов")
        logger.info(f"🖼️ Изображение: {'Да' if post_data.get('image_url') else 'Нет'}")
        
        # Проверяем доступность группы перед публикацией
        try:
            chat = await bot.get_chat(group_id)
            logger.info(f"✅ Группа доступна: {chat.title} (тип: {chat.type})")
        except Exception as e:
            error_msg = str(e).lower()
            logger.error(f"❌ Ошибка доступа к группе {group_id}: {e}")
            
            if "chat not found" in error_msg or "chat_id is empty" in error_msg:
                raise ValueError(
                    f"Группа не найдена! Проверьте, что:\n"
                    f"1. Бот добавлен в группу\n"
                    f"2. GROUP_ID правильный (используйте /chatid в группе)\n"
                    f"3. Группа не была удалена"
                )
            elif "forbidden" in error_msg or "not enough rights" in error_msg:
                raise ValueError(
                    f"У бота нет прав в группе! Сделайте бота администратором группы."
                )
            else:
                raise
        
        # Telegram ограничивает caption до 1024 символов
        MAX_CAPTION_LENGTH = 1024
        
        # Если есть изображение
        image_url = post_data.get('image_url')
        if image_url and image_url.strip():
            logger.info(f"🔗 URL изображения: {image_url}")
            # Скачиваем изображение
            image_filename = f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            logger.info(f"💾 Скачиваю изображение: {image_filename}")
            image_path = download_image(image_url, image_filename)
            
            if image_path:
                logger.info(f"✅ Изображение скачано: {image_path}")
                photo = FSInputFile(image_path)
                
                # Если текст длиннее 1024 символов - публикуем в два сообщения
                if len(content) > MAX_CAPTION_LENGTH:
                    # Отправляем изображение с коротким caption
                    short_caption = content[:MAX_CAPTION_LENGTH-50] + "...\n\n👇 Читать полностью ниже"
                    logger.info(f"📤 Отправляю изображение с сокращенным текстом...")
                    message = await bot.send_photo(
                        chat_id=group_id,
                        photo=photo,
                        caption=short_caption
                    )
                    # Отправляем полный текст отдельным сообщением
                    logger.info(f"📤 Отправляю полный текст отдельным сообщением...")
                    await bot.send_message(
                        chat_id=group_id,
                        text=content
                    )
                    logger.info(f"✅ Пост опубликован с изображением в двух сообщениях (ID: {message.message_id})")
                else:
                    # Отправляем пост с изображением и полным текстом
                    logger.info(f"📤 Отправляю пост с изображением и текстом...")
                    message = await bot.send_photo(
                        chat_id=group_id,
                        photo=photo,
                        caption=content
                    )
                    logger.info(f"✅ Пост опубликован с изображением (ID: {message.message_id})")
                
                return message.message_id
            else:
                logger.warning(f"⚠️ Не удалось скачать изображение, публикую без него")
        
        # Если изображения нет или не удалось скачать
        logger.info(f"📤 Отправляю текстовый пост без изображения...")
        message = await bot.send_message(
            chat_id=group_id,
            text=content
        )
        logger.info(f"✅ Пост опубликован без изображения (ID: {message.message_id})")
        return message.message_id
        
    except ValueError as e:
        logger.error(f"❌ Ошибка валидации: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка публикации поста: {e}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def scheduled_post_job(bot: Bot):
    """
    Задача для планировщика: генерация и публикация нового поста
    
    Args:
        bot: Экземпляр Telegram бота
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"🕐 Запуск запланированной публикации: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"{'='*60}\n")
    
    try:
        # Проверяем, есть ли неопубликованные посты
        unpublished = get_unpublished_posts()
        
        if unpublished:
            # Используем последний созданный пост (первый в отсортированном списке)
            post = unpublished[0]
            post_data = {
                'content': post.content,
                'image_url': post.image_url if post.image_url else None
            }
            logger.info(f"📄 Используем существующий пост ID: {post.id}, тема: {post.topic}")
            logger.info(f"   Создан: {post.created_at}")
            logger.info(f"   Изображение: {'Есть' if post.image_url else 'Нет'}")
        else:
            # Генерируем новый пост
            logger.info("🔄 Генерируем новый пост...")
            post_data = generate_complete_post()
            
            # Сохраняем в базу данных
            from models import add_post
            post = add_post(
                topic=post_data['topic'],
                content=post_data['content'],
                image_url=post_data['image_url'],
                image_prompt=post_data['image_prompt']
            )
            logger.info(f"💾 Пост сохранен в БД с ID: {post.id}")
        
        # Публикуем пост
        message_id = await publish_post_to_telegram(bot, post_data)
        
        if message_id:
            # Отмечаем пост как опубликованный
            mark_post_published(post.id, message_id)
            logger.info(f"✅ Пост успешно опубликован и отмечен в БД")
            
            # Обновляем время последнего запуска расписания
            schedule = get_active_schedule()
            if schedule:
                update_schedule_last_run(schedule.id)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в задаче планировщика: {e}")
        import traceback
        logger.error(traceback.format_exc())


def setup_scheduler(bot: Bot):
    """
    Настройка планировщика на основе расписания из БД
    
    Args:
        bot: Экземпляр Telegram бота
    """
    schedule = get_active_schedule()
    
    if not schedule:
        logger.warning("⚠️ Активное расписание не найдено")
        return False
    
    try:
        # Парсим время
        hour, minute = map(int, schedule.time.split(':'))
        
        # Создаем триггер в зависимости от частоты
        if schedule.frequency == 'daily':
            # Каждый день в указанное время
            trigger = CronTrigger(
                hour=hour,
                minute=minute,
                timezone="Europe/Moscow"
            )
            logger.info(f"📅 Расписание: Ежедневно в {schedule.time}")
            
        elif schedule.frequency == 'weekly':
            # По определенным дням недели
            if schedule.days_of_week:
                days = schedule.days_of_week
                trigger = CronTrigger(
                    day_of_week=days,
                    hour=hour,
                    minute=minute,
                    timezone="Europe/Moscow"
                )
                logger.info(f"📅 Расписание: Еженедельно в {schedule.time} по дням: {days}")
            else:
                logger.warning("⚠️ Для weekly не указаны дни недели")
                return False
        else:
            logger.warning(f"⚠️ Неизвестная частота: {schedule.frequency}")
            return False
        
        # Добавляем задачу в планировщик
        scheduler.add_job(
            scheduled_post_job,
            trigger=trigger,
            args=[bot],
            id='post_publication',
            replace_existing=True,
            misfire_grace_time=3600  # 1 час на случай пропуска
        )
        
        logger.info(f"✅ Планировщик настроен и запущен")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка настройки планировщика: {e}")
        return False


def start_scheduler():
    """Запуск планировщика"""
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Планировщик запущен")


def stop_scheduler():
    """Остановка планировщика"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("⏸️ Планировщик остановлен")


def add_default_schedule():
    """Добавление расписания по умолчанию в БД"""
    from models import Schedule, SessionLocal
    
    db = SessionLocal()
    try:
        # Проверяем, есть ли уже расписание
        existing = db.query(Schedule).first()
        if existing:
            logger.info("ℹ️ Расписание уже существует")
            return existing
        
        # Создаем новое расписание
        schedule = Schedule(
            frequency=config.DEFAULT_POST_FREQUENCY,
            time=config.DEFAULT_POST_TIME,
            is_active=True
        )
        db.add(schedule)
        db.commit()
        db.refresh(schedule)
        
        logger.info(f"✅ Создано расписание по умолчанию: {schedule.frequency} в {schedule.time}")
        return schedule
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Ошибка создания расписания: {e}")
        return None
    finally:
        db.close()


# Пример использования
if __name__ == "__main__":
    print("🧪 Тестирование планировщика")
    
    # Добавляем расписание по умолчанию
    add_default_schedule()
    
    # Показываем активное расписание
    schedule = get_active_schedule()
    if schedule:
        print(f"\n📋 Активное расписание:")
        print(f"  - Частота: {schedule.frequency}")
        print(f"  - Время: {schedule.time}")
        print(f"  - Последний запуск: {schedule.last_run}")

