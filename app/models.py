from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"
    user_id       = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(120), nullable=False)
    email         = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    books           = db.relationship("Book",           backref="owner", lazy="dynamic", cascade="all, delete-orphan")
    highlights      = db.relationship("Highlight",      backref="user",  lazy="dynamic", cascade="all, delete-orphan")
    recommendations = db.relationship("Recommendation", backref="user",  lazy="dynamic", cascade="all, delete-orphan")

    def get_id(self): return str(self.user_id)
    def set_password(self, p): self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)


class Book(db.Model):
    __tablename__ = "books"
    book_id           = db.Column(db.Integer, primary_key=True)
    user_id           = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True)
    book_title        = db.Column(db.String(512), nullable=False)
    pdf_path          = db.Column(db.String(1024), nullable=False)
    upload_date       = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    processing_status = db.Column(db.String(24), default="processing", nullable=False, index=True)
    processing_error  = db.Column(db.Text, nullable=True)
    processed_at      = db.Column(db.DateTime, nullable=True)
    chapters        = db.relationship("Chapter",        backref="book", lazy="dynamic", cascade="all, delete-orphan")
    category        = db.relationship("Category",       backref="book", uselist=False,  cascade="all, delete-orphan")
    recommendations = db.relationship("Recommendation", backref="book", lazy="dynamic", cascade="all, delete-orphan")


class Chapter(db.Model):
    __tablename__ = "chapters"
    chapter_id    = db.Column(db.Integer, primary_key=True)
    book_id       = db.Column(db.Integer, db.ForeignKey("books.book_id"), nullable=False, index=True)
    chapter_title = db.Column(db.String(512), nullable=False)
    order_index   = db.Column(db.Integer, default=0, nullable=False)
    summary    = db.relationship("Summary",    backref="chapter", uselist=False, cascade="all, delete-orphan")
    vocabulary = db.relationship("Vocabulary", backref="chapter", lazy="dynamic", cascade="all, delete-orphan")


class Summary(db.Model):
    __tablename__ = "summaries"
    summary_id   = db.Column(db.Integer, primary_key=True)
    chapter_id   = db.Column(db.Integer, db.ForeignKey("chapters.chapter_id"), unique=True, nullable=False)
    summary_text = db.Column(db.Text, nullable=False)
    model_name   = db.Column(db.String(120), nullable=False, default="fallback-extractive")
    created_at   = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    highlights   = db.relationship("Highlight", backref="summary", lazy="dynamic", cascade="all, delete-orphan")


class Category(db.Model):
    __tablename__ = "categories"
    category_id   = db.Column(db.Integer, primary_key=True)
    book_id       = db.Column(db.Integer, db.ForeignKey("books.book_id"), nullable=False, index=True)
    category_name = db.Column(db.String(100), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Highlight(db.Model):
    __tablename__ = "highlights"
    highlight_id     = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True)
    summary_id       = db.Column(db.Integer, db.ForeignKey("summaries.summary_id"), nullable=False, index=True)
    highlighted_text = db.Column(db.Text, nullable=False)
    color            = db.Column(db.String(20), default="yellow")
    created_at       = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Vocabulary(db.Model):
    __tablename__ = "vocabulary"
    vocab_id   = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey("chapters.chapter_id"), nullable=False, index=True)
    word       = db.Column(db.String(100), nullable=False)
    definition = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Recommendation(db.Model):
    __tablename__ = "recommendations"
    recommendation_id = db.Column(db.Integer, primary_key=True)
    user_id           = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True)
    book_id           = db.Column(db.Integer, db.ForeignKey("books.book_id"), nullable=False, index=True)
    suggested_title   = db.Column(db.String(512), nullable=False)
    suggested_author  = db.Column(db.String(255), nullable=True)
    reason            = db.Column(db.Text, nullable=True)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)