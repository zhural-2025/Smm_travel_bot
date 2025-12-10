"""
HTTP API сервер для интеграции с Make.com
Позволяет Make вызывать функции бота через HTTP запросы
"""
import asyncio
import logging
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

from config import config
from generators import generate_complete_post
from models import add_post, mark_post_published, get_unpublished_posts
from scheduler import publish_post_to_telegram
from bot import bot, dp
from aiogram.types import Update

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SMM Travel Bot API", version="1.0.0")

# Простой API ключ для безопасности (можно задать в .env)
API_KEY = config.OPENAI_API_KEY[:10] if config.OPENAI_API_KEY else "default_key_12345"


class GenerateRequest(BaseModel):
    """Модель запроса на генерацию поста"""
    topic: Optional[str] = None
    publish: bool = True  # Автоматически публиковать после генерации
    api_key: Optional[str] = None  # Опциональный API ключ для безопасности


class PublishRequest(BaseModel):
    """Модель запроса на публикацию"""
    post_id: Optional[int] = None  # ID поста для публикации, если None - последний неопубликованный
    api_key: Optional[str] = None


class PublishContentRequest(BaseModel):
    """Модель запроса на публикацию готового контента от Make.com"""
    content: str  # Текст поста
    image_url: Optional[str] = None  # URL изображения (опционально)
    topic: Optional[str] = None  # Тема поста (для сохранения в БД, опционально)
    save_to_db: bool = False  # Сохранять ли пост в БД


@app.get("/")
async def root():
    """Главная страница API"""
    return {
        "status": "online",
        "service": "SMM Travel Bot API",
        "version": "1.0.0",
        "endpoints": {
            "GET /api/make_topic": "Получить тему от бота (для Make)",
            "POST /api/generate": "Генерация и публикация поста",
            "POST /api/publish_content": "Публикация готового контента от Make.com",
            "GET /api/status": "Статус API",
            "POST /api/publish": "Публикация существующего поста",
            "GET /api/posts/unpublished": "Список неопубликованных постов"
        }
    }


@app.get("/api/status")
async def status():
    """Проверка статуса API"""
    return {
        "status": "online",
        "bot_connected": True,
        "timestamp": asyncio.get_event_loop().time()
    }


@app.post("/api/generate")
async def generate_post(request: GenerateRequest):
    """
    Генерация и публикация поста через API
    Используется Make.com для автоматизации
    
    Body:
    - topic (optional): Тема поста
    - publish (optional, default=True): Автоматически публиковать после генерации
    - api_key (optional): API ключ для безопасности
    """
    try:
        logger.info(f"📥 Получен запрос на генерацию поста. Тема: {request.topic}")
        
        # Генерация поста
        post_data = generate_complete_post(topic=request.topic)
        
        # Сохранение в БД
        post = add_post(
            topic=post_data.get('topic', request.topic or 'Случайная тема'),
            content=post_data['content'],
            image_url=post_data.get('image_url'),
            image_prompt=post_data.get('image_prompt')
        )
        
        logger.info(f"✅ Пост сгенерирован. ID: {post.id}, Тема: {post.topic}")
        
        # Если нужно опубликовать
        message_id = None
        if request.publish:
            try:
                message_id = await publish_post_to_telegram(bot, post_data)
                if message_id:
                    mark_post_published(post.id, message_id)
                    logger.info(f"✅ Пост опубликован. Telegram ID: {message_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка публикации: {e}")
                # Не возвращаем ошибку, если генерация прошла успешно
        
        return {
            "success": True,
            "post_id": post.id,
            "topic": post.topic,
            "content_preview": post_data['content'][:200] + "..." if len(post_data['content']) > 200 else post_data['content'],
            "has_image": bool(post_data.get('image_url')),
            "published": bool(message_id),
            "telegram_message_id": message_id
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/publish")
async def publish_post(request: PublishRequest):
    """
    Публикация существующего поста
    
    Body:
    - post_id (optional): ID поста для публикации, если None - последний неопубликованный
    - api_key (optional): API ключ для безопасности
    """
    try:
        from models import Post, SessionLocal
        
        db = SessionLocal()
        try:
            if request.post_id:
                post = db.query(Post).filter(Post.id == request.post_id).first()
                if not post:
                    raise HTTPException(status_code=404, detail=f"Пост с ID {request.post_id} не найден")
            else:
                unpublished = get_unpublished_posts()
                if not unpublished:
                    raise HTTPException(status_code=404, detail="Нет неопубликованных постов")
                post = unpublished[0]
            
            post_data = {
                'content': post.content,
                'image_url': post.image_url if post.image_url else None
            }
            
            message_id = await publish_post_to_telegram(bot, post_data)
            
            if message_id:
                mark_post_published(post.id, message_id)
                return {
                    "success": True,
                    "post_id": post.id,
                    "telegram_message_id": message_id
                }
            else:
                raise HTTPException(status_code=500, detail="Ошибка публикации в Telegram")
                
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка публикации: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/publish_content")
async def publish_content(request: PublishContentRequest):
    """
    Публикация готового контента от Make.com
    Make.com генерирует пост самостоятельно и отправляет его сюда для публикации
    
    Body:
    - content (required): Текст поста для публикации
    - image_url (optional): URL изображения для поста
    - topic (optional): Тема поста (для сохранения в БД)
    - save_to_db (optional, default=False): Сохранять ли пост в базу данных
    """
    try:
        logger.info(f"📥 Получен запрос на публикацию контента от Make.com")
        logger.info(f"📝 Длина контента: {len(request.content)} символов")
        logger.info(f"🖼️ Изображение: {'Да' if request.image_url else 'Нет'}")
        logger.info(f"💾 Сохранить в БД: {request.save_to_db}")
        
        # Формируем данные для публикации
        post_data = {
            'content': request.content,
            'image_url': request.image_url if request.image_url else None
        }
        
        # Публикуем в Telegram
        message_id = await publish_post_to_telegram(bot, post_data)
        
        if not message_id:
            raise HTTPException(status_code=500, detail="Ошибка публикации в Telegram")
        
        result = {
            "success": True,
            "telegram_message_id": message_id,
            "published": True
        }
        
        # Если нужно сохранить в БД
        if request.save_to_db:
            try:
                post = add_post(
                    topic=request.topic or "Пост от Make.com",
                    content=request.content,
                    image_url=request.image_url,
                    image_prompt=None
                )
                mark_post_published(post.id, message_id)
                result["post_id"] = post.id
                logger.info(f"✅ Пост сохранен в БД с ID: {post.id}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось сохранить в БД: {e}")
                # Не возвращаем ошибку, так как публикация прошла успешно
        
        logger.info(f"✅ Контент успешно опубликован. Telegram ID: {message_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка публикации контента: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/posts/unpublished")
async def get_unpublished():
    """Получить список неопубликованных постов"""
    try:
        unpublished = get_unpublished_posts()
        return {
            "success": True,
            "count": len(unpublished),
            "posts": [
                {
                    "id": post.id,
                    "topic": post.topic,
                    "created_at": post.created_at.isoformat(),
                    "has_image": bool(post.image_url)
                }
                for post in unpublished[:10]  # Первые 10
            ]
        }
    except Exception as e:
        logger.error(f"❌ Ошибка получения постов: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(config.WEBHOOK_PATH if config.WEBHOOK_PATH and config.USE_WEBHOOK else "/webhook/telegram")
async def telegram_webhook(request: dict, x_telegram_bot_api_secret_token: Optional[str] = Header(None)):
    """
    Endpoint для приема webhook от Telegram
    Используется вместо polling для совместимости с Make.com
    """
    try:
        # Проверка секретного токена (если настроен)
        if config.WEBHOOK_SECRET:
            if x_telegram_bot_api_secret_token != config.WEBHOOK_SECRET:
                logger.warning("❌ Неверный секретный токен webhook")
                raise HTTPException(status_code=403, detail="Invalid secret token")
        
        logger.debug(f"📥 Получен webhook от Telegram: {request}")
        
        # Создаем Update объект из данных webhook
        update = Update(**request)
        
        # Обрабатываем обновление через диспетчер
        await dp.feed_update(bot, update)
        
        logger.debug("✅ Webhook обработан успешно")
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки webhook: {e}", exc_info=True)
        # Возвращаем 200 даже при ошибке, чтобы Telegram не повторял запрос
        return {"ok": False, "error": str(e)}


@app.get("/api/make_topic")
async def get_make_topic():
    """
    Получить сохраненную тему от бота (для Make)
    Тема сохраняется командой /make_topic в боте
    Файл удаляется после первого чтения (одноразовое использование)
    """
    import json
    import os
    
    # Получаем абсолютный путь к файлу
    base_dir = os.path.dirname(os.path.abspath(__file__))
    topic_file = os.path.join(base_dir, "make_topic_request.json")
    
    try:
        if os.path.exists(topic_file):
            with open(topic_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                topic = data.get("topic", "Не указана")
                # Удаляем файл после прочтения (чтобы тема использовалась один раз)
                os.remove(topic_file)
                logger.info(f"📥 Make получил тему через API: {topic}")
                return data
        else:
            logger.debug("📭 Запрос темы через API, но тема не задана")
            return {"topic": None, "message": "Тема не задана"}
    except Exception as e:
        logger.error(f"❌ Ошибка чтения темы: {e}", exc_info=True)
        return {"topic": None, "error": str(e)}


async def run_bot():
    """Запуск Telegram бота с автоматическим перезапуском при ошибках"""
    from bot import main as bot_main
    
    while True:
        try:
            logger.info("🤖 Запуск Telegram бота...")
            await bot_main()
        except Exception as e:
            logger.error(f"❌ Ошибка в работе бота: {e}", exc_info=True)
            logger.info("🔄 Перезапуск бота через 10 секунд...")
            await asyncio.sleep(10)


async def run_api_server(host=None, port=None):
    """Запуск API сервера"""
    host = host or config.API_HOST
    port = port or config.API_PORT
    logger.info(f"🚀 Запуск API сервера на {host}:{port}")
    uvicorn_config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(uvicorn_config)
    await server.serve()


async def run_both():
    """Запуск бота и API сервера одновременно"""
    logger.info("🚀 Запуск бота и API сервера...")
    
    # Запускаем оба сервиса параллельно
    # Если один упадет, другой продолжит работать
    try:
        results = await asyncio.gather(
            run_bot(),
            run_api_server(),
            return_exceptions=True  # Не останавливать другие задачи при ошибке
        )
        
        # Проверяем результаты
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                if i == 0:
                    logger.error(f"❌ Критическая ошибка в боте: {result}", exc_info=True)
                else:
                    logger.error(f"❌ Критическая ошибка в API сервере: {result}", exc_info=True)
                    
        logger.warning("⚠️ Оба сервиса завершились. Завершение программы.")
        
    except KeyboardInterrupt:
        logger.info("⏸️ Получен сигнал остановки...")
        raise
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в run_both: {e}", exc_info=True)
        # Пытаемся перезапустить через 30 секунд
        logger.info("🔄 Попытка перезапуска через 30 секунд...")
        await asyncio.sleep(30)
        # Рекурсивный вызов (будет перезапущено systemd)
        await run_both()


def run_api_server_only(host=None, port=None):
    """Запуск только API сервера (для тестирования)"""
    host = host or config.API_HOST
    port = port or config.API_PORT
    logger.info(f"🚀 Запуск API сервера на {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    # Запускаем и бота, и API сервер одновременно
    try:
        asyncio.run(run_both())
    except KeyboardInterrupt:
        logger.info("⏸️ Остановка сервисов...")

