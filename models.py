"""
Модели данных для хранения постов и расписания публикаций
"""
import os
import stat
import logging
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, or_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import config

Base = declarative_base()
logger = logging.getLogger(__name__)

class Post(Base):
    """Модель для хранения сгенерированных постов"""
    __tablename__ = 'posts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    topic = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    image_url = Column(String(500), nullable=True)
    image_prompt = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
    is_published = Column(Boolean, default=False, nullable=True)  # nullable=True для совместимости со старыми записями
    telegram_message_id = Column(Integer, nullable=True)
    
    def __repr__(self):
        return f"<Post(id={self.id}, topic='{self.topic}', is_published={self.is_published})>"


class Schedule(Base):
    """Модель для хранения расписания публикаций"""
    __tablename__ = 'schedules'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    frequency = Column(String(50), nullable=False)  # daily, weekly, custom
    time = Column(String(10), nullable=False)  # формат HH:MM
    days_of_week = Column(String(50), nullable=True)  # для weekly: "1,3,5" (пн, ср, пт)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_run = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Schedule(id={self.id}, frequency='{self.frequency}', time='{self.time}')>"


class Analytics(Base):
    """Модель для хранения аналитики постов"""
    __tablename__ = 'analytics'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, nullable=False)
    views = Column(Integer, default=0)
    forwards = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Analytics(post_id={self.post_id}, views={self.views})>"


# Функция для исправления прав доступа к файлу БД
def fix_db_permissions(db_path: str):
    """Исправление прав доступа к файлу базы данных"""
    try:
        if os.path.exists(db_path):
            # Устанавливаем права на чтение и запись для владельца, группы и остальных
            os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)
            logger.info(f"✅ Права доступа к БД установлены: {db_path}")
        # Также исправляем права на директорию
        db_dir = os.path.dirname(os.path.abspath(db_path)) or '.'
        if os.path.exists(db_dir):
            os.chmod(db_dir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
    except Exception as e:
        logger.warning(f"⚠️ Не удалось установить права доступа к БД: {e}")

# Извлекаем путь к файлу БД из DATABASE_URL
db_path = None
if config.DATABASE_URL and config.DATABASE_URL.startswith('sqlite'):
    # Извлекаем путь из sqlite:///./travel_bot.db или sqlite:///travel_bot.db
    db_path = config.DATABASE_URL.replace('sqlite:///', '').replace('sqlite://', '')
    if db_path.startswith('./'):
        db_path = db_path[2:]
    if not db_path:
        db_path = 'travel_bot.db'
    
    # Исправляем права при запуске
    try:
        fix_db_permissions(db_path)
    except Exception as e:
        logger.warning(f"⚠️ Предупреждение при проверке прав БД: {e}")

# Создание движка базы данных
engine = create_engine(config.DATABASE_URL, echo=False)

# Создание всех таблиц
Base.metadata.create_all(engine)

# Повторно проверяем права после создания таблиц
if db_path:
    try:
        fix_db_permissions(db_path)
    except Exception as e:
        logger.warning(f"⚠️ Предупреждение при проверке прав БД: {e}")

# Создание фабрики сессий
SessionLocal = sessionmaker(bind=engine)


def get_db():
    """Получение сессии базы данных"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass


def init_db():
    """Инициализация базы данных"""
    try:
        Base.metadata.create_all(engine)
        # Исправляем права после создания
        if db_path:
            fix_db_permissions(db_path)
        # Исправляем NULL значения в is_published (если есть)
        try:
            fixed = fix_null_is_published()
            if fixed > 0:
                logger.info(f"✅ Исправлено {fixed} записей с NULL в is_published при инициализации БД")
        except Exception as e:
            logger.warning(f"⚠️ Предупреждение при исправлении NULL значений: {e}")
            # Продолжаем работу даже если исправление не удалось
        logger.info("База данных инициализирована")
    except PermissionError as e:
        logger.error(f"❌ Ошибка прав доступа к БД: {e}")
        logger.error("💡 Попробуйте выполнить на сервере: chmod 666 travel_bot.db")
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        raise


def add_post(topic: str, content: str, image_url: str = None, image_prompt: str = None, is_published: bool = False):
    """Добавление нового поста в базу данных"""
    db = SessionLocal()
    try:
        # Явно устанавливаем is_published=False для всех новых постов (если не указано иное)
        post = Post(
            topic=topic,
            content=content,
            image_url=image_url,
            image_prompt=image_prompt,
            is_published=is_published  # Явно устанавливаем значение
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        
        # Логируем создание поста для диагностики
        logger.info(f"💾 Пост создан: ID={post.id}, topic='{topic[:30]}...', is_published={post.is_published}, тип={type(post.is_published)}")
        
        # Дополнительная проверка: если после сохранения значение не False/0/None, выводим предупреждение
        if post.is_published not in (False, None, 0):
            logger.warning(f"⚠️ Пост ID={post.id} создан с is_published={post.is_published} вместо False!")
        
        return post
    except PermissionError as e:
        logger.error(f"❌ Ошибка прав доступа при добавлении поста: {e}")
        db.rollback()
        # Пытаемся исправить права и повторить
        if db_path:
            try:
                fix_db_permissions(db_path)
                db.commit()
                db.refresh(post)
                logger.info("✅ Права исправлены, пост добавлен")
                return post
            except:
                pass
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении поста: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def fix_null_is_published():
    """Исправить NULL значения в поле is_published (установить False для всех NULL)"""
    db = SessionLocal()
    try:
        # Находим все записи с NULL значением
        posts_with_null = db.query(Post).filter(Post.is_published.is_(None)).all()
        fixed_count = 0
        for post in posts_with_null:
            post.is_published = False
            fixed_count += 1
        if fixed_count > 0:
            db.commit()
            logger.info(f"✅ Исправлено {fixed_count} записей с NULL в is_published")
        return fixed_count
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Ошибка при исправлении NULL значений: {e}")
        # Не поднимаем исключение, чтобы не блокировать инициализацию
        return 0
    finally:
        db.close()


def get_posts_diagnostic():
    """Диагностическая информация о постах в БД"""
    db = SessionLocal()
    try:
        total = db.query(Post).count()
        published_true = db.query(Post).filter(Post.is_published.is_(True)).count()
        published_false = db.query(Post).filter(Post.is_published.is_(False)).count()
        published_null = db.query(Post).filter(Post.is_published.is_(None)).count()
        
        return {
            'total': total,
            'published_true': published_true,
            'published_false': published_false,
            'published_null': published_null
        }
    finally:
        db.close()


def get_unpublished_posts():
    """Получение неопубликованных постов, отсортированных по дате создания (последние сначала)"""
    from sqlalchemy import case
    db = SessionLocal()
    try:
        # В SQLite Boolean хранится как INTEGER (0 или 1) или NULL
        # Используем более явное сравнение для совместимости с SQLite
        # Неопубликованные посты: is_published IS NULL, is_published = 0, или is_published = False
        
        # Сначала получаем все посты и фильтруем в Python для надежности
        # Это гарантирует работу независимо от того, как SQLite хранит Boolean
        all_posts = db.query(Post).order_by(Post.created_at.desc()).all()
        
        unpublished = []
        for post in all_posts:
            # Проверяем все возможные варианты "неопубликовано"
            if (post.is_published is None or 
                post.is_published is False or 
                post.is_published == 0 or
                post.is_published == False):
                unpublished.append(post)
        
        logger.info(f"📊 Всего постов: {len(all_posts)}, неопубликованных: {len(unpublished)}")
        if unpublished:
            logger.info(f"   Первый неопубликованный: ID {unpublished[0].id}, is_published={unpublished[0].is_published}, тип={type(unpublished[0].is_published)}")
        
        return unpublished
    except Exception as e:
        logger.error(f"❌ Ошибка получения неопубликованных постов: {e}", exc_info=True)
        return []
    finally:
        db.close()


def mark_post_published(post_id: int, message_id: int):
    """Отметить пост как опубликованный"""
    db = SessionLocal()
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        if post:
            post.is_published = True
            post.published_at = datetime.utcnow()
            post.telegram_message_id = message_id
            db.commit()
            return True
        return False
    except PermissionError as e:
        logger.error(f"❌ Ошибка прав доступа при обновлении поста: {e}")
        db.rollback()
        if db_path:
            try:
                fix_db_permissions(db_path)
                db.commit()
                logger.info("✅ Права исправлены, пост обновлен")
                return True
            except:
                pass
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении поста: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def get_active_schedule():
    """Получение активного расписания"""
    db = SessionLocal()
    try:
        # Используем .is_(True) для правильной работы с Boolean типом в SQLAlchemy
        return db.query(Schedule).filter(Schedule.is_active.is_(True)).first()
    finally:
        db.close()


def update_schedule_last_run(schedule_id: int):
    """Обновление времени последнего запуска расписания"""
    db = SessionLocal()
    try:
        schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
        if schedule:
            schedule.last_run = datetime.utcnow()
            db.commit()
            return True
        return False
    except PermissionError as e:
        logger.error(f"❌ Ошибка прав доступа при обновлении расписания: {e}")
        db.rollback()
        if db_path:
            try:
                fix_db_permissions(db_path)
                db.commit()
                logger.info("✅ Права исправлены, расписание обновлено")
                return True
            except:
                pass
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении расписания: {e}")
        db.rollback()
        raise
    finally:
        db.close()

