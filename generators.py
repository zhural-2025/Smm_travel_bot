"""
Генераторы контента для SMM-бота с использованием OpenAI API
"""
import random
import requests
import logging
from openai import OpenAI
from config import config

# Настройка логирования
logger = logging.getLogger(__name__)

# Инициализация клиента OpenAI
client = OpenAI(api_key=config.OPENAI_API_KEY)


def generate_post_text(topic: str = None) -> dict:
    """
    Генерация текста поста о путешествиях
    
    Args:
        topic: Тема поста (опционально). Если не указана, выбирается случайно
        
    Returns:
        dict: Словарь с ключами 'topic', 'content', 'image_prompt'
    """
    if not topic:
        topic = random.choice(config.TRAVEL_TOPICS)
    
    prompt = f"""Ты - SMM-эксперт, который создает контент для блога о путешествиях в Telegram.
    
Создай интересный и вовлекающий пост на тему: "{topic}"

Требования к посту:
- Длина: 150-250 слов (ВАЖНО: НЕ БОЛЕЕ 250 слов!)
- Максимум 900 символов
- Стиль: живой, дружелюбный, информативный
- Структура: заголовок с эмодзи, основной текст с полезной информацией, призыв к действию
- Используй релевантные эмодзи для визуального разнообразия
- Добавь 2-3 практических совета или интересных факта
- Избегай банальностей
- Будь кратким и емким

Формат ответа: только текст поста, без дополнительных комментариев."""

    try:
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты - профессиональный SMM-менеджер для блога о путешествиях. Пиши кратко и по делу."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=600
        )
        
        content = response.choices[0].message.content.strip()
        
        # Генерация промпта для изображения
        image_prompt = generate_image_prompt(topic, content)
        
        return {
            'topic': topic,
            'content': content,
            'image_prompt': image_prompt
        }
        
    except Exception as e:
        print(f"❌ Ошибка генерации текста: {e}")
        return {
            'topic': topic,
            'content': f"Ошибка генерации контента: {str(e)}",
            'image_prompt': None
        }


def generate_image_prompt(topic: str, post_content: str) -> str:
    """
    Генерация промпта для создания изображения на основе текста поста
    
    Args:
        topic: Тема поста
        post_content: Содержание поста
        
    Returns:
        str: Промпт для DALL-E
    """
    prompt = f"""На основе следующего поста о путешествиях создай промпт для DALL-E (НА АНГЛИЙСКОМ ЯЗЫКЕ) для генерации РЕАЛЬНОЙ ФОТОГРАФИИ, а НЕ рисунка:

Тема: {topic}
Пост: {post_content[:500]}

КРИТИЧЕСКИ ВАЖНО: Промпт ДОЛЖЕН начинаться со слов "A real photograph" или "Professional travel photograph" или "DSLR photograph"

Обязательно включи в промпт:
- "real photograph" или "DSLR photograph" или "professional travel photography"
- Технические термины: "shot with Canon/Nikon DSLR", "35mm lens", "f/2.8", "ISO 100"
- "photorealistic", "high resolution", "natural lighting"
- Детали сцены по теме поста

ЗАПРЕЩЕНО использовать:
- "illustration", "drawing", "artistic", "painting", "digital art", "rendering", "3D render"
- Любые слова связанные с искусством или иллюстрацией

Длина промпта: 50-150 слов на английском языке.
Формат ответа: ТОЛЬКО промпт без дополнительных комментариев, без кавычек."""

    try:
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты создаешь промпты ТОЛЬКО для реальных фотографий. ВСЕГДА начинай промпт со слов 'A real photograph' или 'Professional photograph' или 'DSLR photograph'. НИКОГДА не используй слова 'illustration', 'drawing', 'artistic', 'painting'. Включи технические фото-термины: DSLR, lens, aperture, ISO."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=300
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"❌ Ошибка генерации промпта для изображения: {e}")
        return f"A real photograph of {topic}, professional travel photography, shot with DSLR camera, 35mm lens, natural lighting, high resolution, photorealistic, vibrant colors"


def generate_image(prompt: str) -> str:
    """
    Генерация изображения с помощью DALL-E (реалистичная фотография)
    
    Args:
        prompt: Текстовое описание изображения
        
    Returns:
        str: URL сгенерированного изображения или None
    """
    try:
        # Убеждаемся, что промпт явно указывает на реальную фотографию
        prompt_lower = prompt.lower()
        
        # Проверяем и исправляем промпт, если нужно
        if not any(word in prompt_lower for word in ["real photograph", "dslr photograph", "professional photograph", "photograph taken"]):
            # Если промпт не начинается с указания на фото, добавляем в начало
            if not prompt_lower.startswith(("a real", "professional", "dslr")):
                prompt = f"A real photograph, {prompt}"
        
        # Удаляем слова, связанные с рисунками, если они есть
        art_words = ["illustration", "drawing", "artistic", "painting", "digital art", "rendering"]
        for word in art_words:
            if word in prompt_lower:
                prompt = prompt.replace(word, "").replace(word.capitalize(), "")
                print(f"⚠️ Удалено слово '{word}' из промпта")
        
        # Добавляем технические фото-термины, если их нет
        if "dslr" not in prompt_lower and "camera" not in prompt_lower:
            prompt = f"{prompt}, shot with professional DSLR camera, natural lighting"
        
        print(f"🎨 Промпт для DALL-E: {prompt}")
        
        response = client.images.generate(
            model=config.DALLE_MODEL,
            prompt=prompt,
            size="1024x1024",
            quality="standard",  # Стандартное качество
            n=1
        )
        
        image_url = response.data[0].url
        print(f"✅ Реалистичная фотография сгенерирована: {image_url}")
        return image_url
        
    except Exception as e:
        print(f"❌ Ошибка генерации изображения: {e}")
        return None


def download_image(url: str, filename: str) -> str:
    """
    Скачивание изображения по URL
    
    Args:
        url: URL изображения
        filename: Имя файла для сохранения
        
    Returns:
        str: Путь к сохраненному файлу или None
    """
    import os
    
    try:
        if not url or not url.strip():
            logger.warning("❌ URL изображения пустой")
            return None
            
        logger.info(f"📥 Скачиваю изображение с URL: {url[:50]}...")
        response = requests.get(url, timeout=30)
        
        # Проверяем статус ответа
        if response.status_code == 403:
            logger.error(f"❌ Ошибка 403: Доступ запрещен. Возможные причины: "
                        f"API ключ OpenAI недействителен или истек срок действия URL изображения")
            return None
        elif response.status_code == 404:
            logger.error(f"❌ Ошибка 404: Изображение не найдено по URL")
            return None
        
        response.raise_for_status()
        
        # Получаем абсолютный путь к директории проекта
        base_dir = os.path.dirname(os.path.abspath(__file__))
        images_dir = os.path.join(base_dir, "images")
        
        # Создаем директорию, если её нет
        os.makedirs(images_dir, exist_ok=True)
        
        filepath = os.path.join(images_dir, filename)
        
        logger.info(f"💾 Сохраняю изображение в: {filepath}")
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        # Проверяем, что файл создан
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            logger.info(f"✅ Изображение сохранено: {filepath} ({file_size} байт)")
            return filepath
        else:
            logger.error(f"❌ Файл не был создан: {filepath}")
            return None
        
    except requests.exceptions.HTTPError as e:
        logger.error(f"❌ HTTP ошибка при скачивании изображения: {e}")
        if hasattr(e.response, 'status_code'):
            logger.error(f"   Код статуса: {e.response.status_code}")
            logger.error(f"   Ответ сервера: {e.response.text[:200]}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка сети при скачивании изображения: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при скачивании изображения: {e}", exc_info=True)
        return None


def generate_complete_post(topic: str = None) -> dict:
    """
    Генерация полного поста (текст + изображение)
    
    Args:
        topic: Тема поста (опционально)
        
    Returns:
        dict: Словарь с полной информацией о посте
    """
    print(f"🔄 Начинаем генерацию поста...")
    
    # Генерируем текст
    post_data = generate_post_text(topic)
    print(f"✅ Текст поста сгенерирован на тему: {post_data['topic']}")
    print(f"📝 Длина текста: {len(post_data['content'])} символов")
    
    # Генерируем изображение
    if post_data.get('image_prompt'):
        print(f"🎨 Генерирую изображение с промптом: {post_data['image_prompt'][:100]}...")
        image_url = generate_image(post_data['image_prompt'])
        if image_url:
            print(f"✅ Изображение сгенерировано: {image_url}")
            post_data['image_url'] = image_url
        else:
            print(f"⚠️ Не удалось сгенерировать изображение")
            post_data['image_url'] = None
    else:
        print(f"⚠️ Промпт для изображения не был создан")
        post_data['image_url'] = None
    
    print(f"📊 Итоговые данные поста:")
    print(f"   - Тема: {post_data.get('topic')}")
    print(f"   - Изображение: {'Есть' if post_data.get('image_url') else 'Нет'}")
    
    return post_data


def generate_content_recommendations() -> dict:
    """
    Генерация рекомендаций по контенту для блога о путешествиях
    
    Returns:
        dict: Словарь с рекомендациями (topics, tips, best_time, engagement_ideas)
    """
    from datetime import datetime
    
    current_month = datetime.now().strftime("%B")
    current_season = get_current_season()
    
    prompt = f"""Ты - SMM-эксперт для блога о путешествиях в Telegram.

Сейчас: {current_month}, {current_season}

Предоставь рекомендации по контенту:

1. **5 АКТУАЛЬНЫХ ТЕМ ДЛЯ ПОСТОВ** (с учетом сезона):
   - Темы, которые сейчас популярны
   - Учитывай текущее время года
   - Праздники и события месяца

2. **3 ИДЕИ ДЛЯ ВОВЛЕЧЕНИЯ АУДИТОРИИ**:
   - Интерактивные форматы
   - Вопросы для подписчиков
   - Конкурсы или опросы

3. **ЛУЧШЕЕ ВРЕМЯ ДЛЯ ПУБЛИКАЦИЙ**:
   - Оптимальные дни недели
   - Лучшие часы для постинга

4. **ТРЕНДЫ В TRAVEL-КОНТЕНТЕ**:
   - Что сейчас популярно
   - Какие форматы работают лучше

Формат: структурированный текст с эмодзи, готовый для отправки в Telegram."""

    try:
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты - профессиональный SMM-консультант для travel-блогов. Давай конкретные, практичные советы."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        recommendations = response.choices[0].message.content.strip()
        
        return {
            'success': True,
            'recommendations': recommendations,
            'season': current_season,
            'month': current_month
        }
        
    except Exception as e:
        print(f"❌ Ошибка генерации рекомендаций: {e}")
        return {
            'success': False,
            'error': str(e),
            'recommendations': None
        }


def generate_topic_ideas(count: int = 5) -> dict:
    """
    Генерация идей для тем постов
    
    Args:
        count: Количество идей
        
    Returns:
        dict: Словарь с идеями тем
    """
    current_season = get_current_season()
    
    prompt = f"""Предложи {count} уникальных и интересных тем для постов в Telegram-блоге о путешествиях.

Текущий сезон: {current_season}

Требования:
- Темы должны быть конкретными (не общими)
- Учитывай сезонность
- Включи разнообразие: советы, места, лайфхаки, истории
- Каждая тема должна быть интересна аудитории

Формат ответа:
1. [Тема] - краткое описание (1 предложение)
2. [Тема] - краткое описание
...

Без лишних комментариев, только список тем."""

    try:
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты - креативный SMM-специалист для travel-блога."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.9,
            max_tokens=500
        )
        
        ideas = response.choices[0].message.content.strip()
        
        return {
            'success': True,
            'ideas': ideas,
            'count': count,
            'season': current_season
        }
        
    except Exception as e:
        print(f"❌ Ошибка генерации идей: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def get_current_season() -> str:
    """Определение текущего сезона"""
    from datetime import datetime
    month = datetime.now().month
    
    if month in [12, 1, 2]:
        return "зима"
    elif month in [3, 4, 5]:
        return "весна"
    elif month in [6, 7, 8]:
        return "лето"
    else:
        return "осень"


def analyze_post_idea(idea: str) -> dict:
    """
    Анализ идеи поста и предложения по улучшению
    
    Args:
        idea: Идея или тема для поста
        
    Returns:
        dict: Анализ и рекомендации
    """
    prompt = f"""Проанализируй эту идею для поста в travel-блоге: "{idea}"

Дай краткий анализ:

1. **ОЦЕНКА ИДЕИ** (1-10): насколько тема интересна аудитории
2. **ЦЕЛЕВАЯ АУДИТОРИЯ**: кому будет интересен этот пост
3. **КАК УЛУЧШИТЬ**: 2-3 совета как сделать пост интереснее
4. **ХЕШТЕГИ**: 5 релевантных хештегов для поста
5. **ЛУЧШИЙ ФОРМАТ**: текст/фото/видео/карусель

Будь кратким и конкретным."""

    try:
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты - SMM-аналитик для travel-контента."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        analysis = response.choices[0].message.content.strip()
        
        return {
            'success': True,
            'idea': idea,
            'analysis': analysis
        }
        
    except Exception as e:
        print(f"❌ Ошибка анализа идеи: {e}")
        return {
            'success': False,
            'error': str(e)
        }


# Пример использования
if __name__ == "__main__":
    # Тест генерации поста
    result = generate_complete_post()
    print("\n" + "="*50)
    print(f"Тема: {result['topic']}")
    print("="*50)
    print(f"\nТекст поста:\n{result['content']}")
    print(f"\nПромпт для изображения:\n{result['image_prompt']}")
    print(f"\nURL изображения: {result['image_url']}")

