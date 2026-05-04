# ChapterLens - AI PDF Book Summarizer

ChapterLens is a Flask-based SaaS-style web app where users upload PDF books and receive chapter-wise summaries stored in their personal library.

## Features

- User registration/login with hashed passwords.
- Personal dashboard and private library per account.
- Drag-and-drop PDF upload with validation.
- Automatic text extraction and chapter detection.
- AI chapter summarization (OpenAI) with extractive fallback.
- Persistent summaries in relational DB (no reprocessing on revisit).
- Processing status page with live progress polling.

## Tech Stack

- Backend: Flask, Flask-Login, Flask-SQLAlchemy
- Database: SQLite (default), PostgreSQL via `DATABASE_URL`
- NLP: OpenAI API (optional), fallback local extractive summarizer
- PDF parsing: `pdfplumber`
- Frontend: Server-rendered HTML/CSS with modern SaaS UI

## Database Design (3NF)

Core entities:

- `users(user_id, name, email, password_hash)`
- `books(book_id, user_id, book_title, pdf_path, upload_date, processing_status, processing_error, processed_at)`
- `chapters(chapter_id, book_id, chapter_title, order_index)`
- `summaries(summary_id, chapter_id, summary_text, model_name, created_at)`

Relations:

- One user has many books
- One book has many chapters
- One chapter has one summary

## Run Locally

1. Create virtual environment and install dependencies:
   - `python -m venv .venv`
   - `.venv\Scripts\activate`
   - `pip install -r requirements.txt`
2. Configure environment:
   - Copy `.env.example` to `.env`
   - Add `OPENAI_API_KEY` if you want model-generated summaries
3. Start app:
   - `python run.py`
4. Open:
   - [http://localhost:5000](http://localhost:5000)

## Deployment Notes

- Render/Railway/AWS ready with env vars:
  - `SECRET_KEY`
  - `DATABASE_URL`
  - `MAX_UPLOAD_MB`
  - `OPENAI_API_KEY` (optional)
  - `OPENAI_SUMMARY_MODEL` (optional)
- For production scale, replace in-process thread processing with Celery/RQ worker + Redis queue.
