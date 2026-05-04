# ChapterLens - AI PDF Book Summarizer

ChapterLens is a Flask-based SaaS-style web app where users upload PDF books and receive chapter-wise summaries stored in their personal library.

## Features

- User registration/login with hashed passwords.
- Personal dashboard and private library per account.
- Drag-and-drop PDF upload with validation.
- Automatic text extraction and chapter detection.
- AI chapter summarization (Claude) with extractive fallback.
- Persistent summaries in relational DB (no reprocessing on revisit).
- Processing status page with live progress polling.

## Tech Stack

- Backend: Flask, Flask-Login, Flask-SQLAlchemy
- Database: SQLite (default), PostgreSQL via `DATABASE_URL`
- API: Claude haiku 4.6 
- PDF parsing: `pdfplumber`
- Frontend: Server-rendered HTML/CSS with modern SaaS UI

## Database Design (3NF)

Core entities:
-users(user_id, name, email, password_hash)
-books(book_id, user_id, book_title, pdf_path, upload_date, processing_status, processing_error, processed_at)
-chapters(chapter_id, book_id, chapter_title, order_index)
-summaries(summary_id, chapter_id, summary_text, model_name, created_at)
-categories(category_id, book_id, category_name, created_at)
-highlights(highlight_id, user_id, summary_id, highlighted_text, color, created_at)
-vocabulary(vocab_id, chapter_id, word, definition, created_at)
-recommendations(recommendation_id, user_id, book_id, suggested_title, suggested_author, reason, created_at)

## Run Locally

1. Create virtual environment and install dependencies:
   - `python -m venv .venv`
   - `.venv\Scripts\activate`
   - `pip install -r requirements.txt`
2. Configure environment:
   - Copy `.env.example` to `.env`
   - Add `API_KEY` 
3. Start app:
   - `python run.py`
4. Open:
   - [http://localhost:5000](http://localhost:5000)

