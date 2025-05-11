from sqlalchemy import create_engine, Column, Integer, String, Text, TIMESTAMP, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy import DateTime
from sqlalchemy import CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.orm import sessionmaker, Session

# Настройка SQLAlchemy
SQLALCHEMY_DATABASE_URL = "sqlite:///./data_bases/main.db" # путь к базе данных (будет там же где и main.py)
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель для пользователей
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True)  # Добавлен unique=True
    email = Column(String, unique=True)
    password_hash = Column(String)
    created_at = Column(TIMESTAMP, server_default=func.now())
    profile_picture = Column(String(255))

    videos = relationship("Video", back_populates="author")
    comments = relationship("Comment", back_populates="user")

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    filepath = Column(String(255), nullable=False)
    thumbnail = Column(String(255))
    views = Column(Integer, server_default="0", nullable=False)
    duration = Column(Integer)
    privacy = Column(String(10), server_default="public")
    created_at = Column(DateTime, server_default=func.now())

    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    author = relationship("User", back_populates="videos")

    comments = relationship("Comment", back_populates="video")
    likes = relationship("Like", back_populates="video")

    __table_args__ = (
        CheckConstraint("privacy IN ('public', 'private')", name='check_privacy'),
    )

class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(Integer, ForeignKey('videos.id', ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    parent_comment_id = Column(Integer, ForeignKey('comments.id', ondelete="CASCADE"))

    # Связи (опционально, для удобства ORM)
    video = relationship("Video", back_populates="comments")
    user = relationship("User", back_populates="comments")
    replies = relationship("Comment", back_populates="parent_comment")
    parent_comment = relationship("Comment", remote_side=[id], back_populates="replies")

class Like(Base):
    __tablename__ = "likes"

    id = Column(Integer, primary_key=True, autoincrement=True)  # autoincrement=True заменяет sqlite_autoincrement
    video_id = Column(Integer, ForeignKey('videos.id', ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    is_like = Column(Boolean, nullable=False)

    # Вариант 1: Кортеж с ограничениями
    __table_args__ = (
        UniqueConstraint('video_id', 'user_id', name='unique_video_like'),  # Один лайк от пользователя на видео
        CheckConstraint("is_like IN (TRUE, FALSE)", name='check_is_like_bool'),
    )

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subscriber_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    channel_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('subscriber_id', 'channel_id', name='unique_subscription'),
        CheckConstraint("subscriber_id != channel_id", name='check_no_self_subscribe'),
    )

class CommentLike(Base):
    __tablename__ = "comment_likes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    comment_id = Column(Integer, ForeignKey('comments.id', ondelete="CASCADE"), nullable=False)
    is_like = Column(Boolean, nullable=False)  # True = лайк, False = дизлайк
    created_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        # Один пользователь — одна реакция на комментарий
        UniqueConstraint('user_id', 'comment_id', name='unique_comment_like'),
    )