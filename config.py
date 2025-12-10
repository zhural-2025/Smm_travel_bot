"""
Модуль конфигурации для SMM-бота о путешествиях
"""
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

class Config:
    """Класс для хранения конфигурации приложения"""
    
    # Telegram настройки
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID')
    ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
    
    # OpenAI настройки
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_MODEL = 'gpt-4o-mini'  # или 'gpt-4' для лучшего качества
    DALLE_MODEL = 'dall-e-3'
    
    # База данных
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./travel_bot.db')
    
    # Настройки по умолчанию
    DEFAULT_POST_FREQUENCY = os.getenv('DEFAULT_POST_FREQUENCY', 'daily')
    DEFAULT_POST_TIME = os.getenv('DEFAULT_POST_TIME', '10:00')
    
    # API настройки для Make.com
    API_HOST = os.getenv('API_HOST', '0.0.0.0')
    API_PORT = int(os.getenv('API_PORT', 8000))
    MAKE_WEBHOOK_URL = os.getenv('MAKE_WEBHOOK_URL', None)  # URL вебхука от Make (для отправки тем)
    
    # Настройки webhook для бота (вместо polling для совместимости с Make.com)
    WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', None)  # Например: https://yourdomain.com или http://your-ip:8000
    WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook/telegram')
    WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', None)  # Секретный токен для безопасности (опционально)
    USE_WEBHOOK = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'  # Использовать webhook вместо polling
    
    # Темы для постов о путешествиях
    TRAVEL_TOPICS = [
        "Советы для путешественников",
        "Интересные места мира",
        "Культурные особенности стран",
        "Бюджетные путешествия",
        "Экзотические направления",
        "Городские достопримечательности",
        "Природные чудеса",
        "Местная кухня и гастрономия",
        "Маршруты и туры",
        "Советы по безопасности в путешествиях",
        "Лайфхаки для туристов",
        "Необычные отели и места проживания"
    ]
    
    @classmethod
    def validate(cls):
        """Проверка наличия обязательных параметров"""
        required_params = {
            'TELEGRAM_BOT_TOKEN': cls.TELEGRAM_BOT_TOKEN,
            'OPENAI_API_KEY': cls.OPENAI_API_KEY,
            'TELEGRAM_GROUP_ID': cls.TELEGRAM_GROUP_ID,
            'ADMIN_ID': cls.ADMIN_ID
        }
        
        missing = [key for key, value in required_params.items() if not value]
        
        if missing:
            raise ValueError(
                f"Отсутствуют обязательные параметры в .env файле: {', '.join(missing)}\n"
                f"Пожалуйста, создайте файл .env на основе .env.example"
            )
        
        return True

# Экспортируем экземпляр конфигурации
config = Config()

