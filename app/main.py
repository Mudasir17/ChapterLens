import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import (
    Blueprint, abort, current_app, flash,
    jsonify, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required

from app.ai_service import summarize_chapter, extract_vocabulary, generate_recommendations, detect_category
from app.extensions import db
from app.models import Book, Chapter, Summary, Category, Vocabulary, Recommendation, Highlight
from app.pdf_service import detect_chapters, extract_text_from_pdf

bp = Blueprint("main", __name__)

_DELAY_BETWEEN_CHAPTERS = 5


def _process_book(app, book_id: int, absolute_pdf_path: str) -> None:
    with app.app_context():
        book = db.session.get(Book, book_id)
        if not book:
            return
        try:
            raw_text = extract_text_from_pdf(Path(absolute_pdf_path))
            chapter_pairs = detect_chapters(raw_text)
            total = len(chapter_pairs)
            print(f"[process_book] Found {total} chapters for book_id={book_id}")

            first_chapter_text = chapter_pairs[0][1] if chapter_pairs else ""

            # Detect & save category
            category_name = detect_category(book.book_title, first_chapter_text)
            db.session.add(Category(book_id=book.book_id, category_name=category_name))
            db.session.commit()
            print(f"[process_book] Category: {category_name}")

            # Process each chapter
            for i, (ch_title, ch_body) in enumerate(chapter_pairs):
                print(f"[process_book] Summarising {i+1}/{total}: {ch_title[:60]}")

                ch = Chapter(
                    book_id=book.book_id,
                    chapter_title=ch_title[:500],
                    order_index=i,
                )
                db.session.add(ch)
                db.session.flush()

                # Summary
                summary_text, model_used = summarize_chapter(ch_title, ch_body)
                db.session.add(Summary(
                    chapter_id=ch.chapter_id,
                    summary_text=summary_text,
                    model_name=model_used[:120],
                ))
                db.session.flush()

                # Vocabulary
                vocab_items = extract_vocabulary(ch_title, ch_body)
                for item in vocab_items:
                    db.session.add(Vocabulary(
                        chapter_id=ch.chapter_id,
                        word=item["word"][:100],
                        definition=item["definition"],
                    ))

                db.session.commit()
                print(f"[process_book] Chapter {i+1} done — {len(vocab_items)} vocab words")

                if i < total - 1:
                    time.sleep(_DELAY_BETWEEN_CHAPTERS)

            # Generate recommendations based on full book
            book_summary = " ".join(
                ch[1][:200] for ch in chapter_pairs[:3]
            )
            recs = generate_recommendations(book.book_title, book_summary)
            for rec in recs:
                db.session.add(Recommendation(
                    user_id=book.user_id,
                    book_id=book.book_id,
                    suggested_title=rec["title"][:512],
                    suggested_author=rec.get("author", "")[:255],
                    reason=rec.get("reason", ""),
                ))
            db.session.commit()
            print(f"[process_book] {len(recs)} recommendations saved")

            book.processing_status = "ready"
            book.processed_at = datetime.utcnow()
            book.processing_error = None
            db.session.commit()
            print(f"[process_book] Book {book_id} complete.")

        except Exception as exc:
            db.session.rollback()
            print(f"[process_book] CRITICAL ERROR: {exc}")
            failed_book = db.session.get(Book, book_id)
            if failed_book:
                failed_book.processing_status = "failed"
                failed_book.processing_error = str(exc)[:4000]
                db.session.commit()
        finally:
            db.session.remove()


# EXISTING ROUTES
@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("landing.html")


@bp.get("/dashboard")
@login_required
def dashboard():
    books = Book.query.filter_by(user_id=current_user.user_id).all()
    ready_books = [b for b in books if b.processing_status == "ready"]
    chapter_count = (
        db.session.query(Chapter)
        .join(Book, Book.book_id == Chapter.book_id)
        .filter(Book.user_id == current_user.user_id)
        .count()
    )
    return render_template(
        "dashboard.html",
        total_books=len(books),
        ready_books=len(ready_books),
        processing_books=len(books) - len(ready_books),
        chapter_count=chapter_count,
    )


@bp.get("/library")
@login_required
def library():
    books = (
        Book.query.filter_by(user_id=current_user.user_id)
        .order_by(Book.upload_date.desc())
        .all()
    )
    return render_template("library.html", books=books)


@bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        f = request.files.get("pdf")
        if not f or not f.filename:
            flash("Please choose a PDF file.", "error")
            return redirect(url_for("main.upload"))
        if not f.filename.lower().endswith(".pdf"):
            flash("Only PDF files are allowed.", "error")
            return redirect(url_for("main.upload"))

        safe_name = f.filename.replace("\\", "_").replace("/", "_")[:200]
        uid = str(uuid.uuid4())
        user_folder = Path(current_app.config["UPLOAD_FOLDER"]) / str(current_user.user_id)
        user_folder.mkdir(parents=True, exist_ok=True)
        rel = f"{current_user.user_id}/{uid}.pdf"
        dest = Path(current_app.config["UPLOAD_FOLDER"]) / rel
        f.save(dest)

        try:
            title = (request.form.get("title") or "").strip() or Path(safe_name).stem
            book = Book(
                user_id=current_user.user_id,
                book_title=title[:500],
                pdf_path=rel,
                processing_status="processing",
            )
            db.session.add(book)
            db.session.commit()

            thread = threading.Thread(
                target=_process_book,
                args=(current_app._get_current_object(), book.book_id, str(dest)),
                daemon=True,
            )
            thread.start()
            return redirect(url_for("main.processing", book_id=book.book_id))

        except Exception as exc:
            db.session.rollback()
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass
            flash(f"Database error: {exc}", "error")
            return redirect(url_for("main.upload"))

    return render_template("upload.html")


@bp.get("/processing/<int:book_id>")
@login_required
def processing(book_id: int):
    book = Book.query.filter_by(book_id=book_id, user_id=current_user.user_id).first()
    if not book:
        abort(404)
    return render_template("processing.html", book=book)


@bp.get("/api/books/<int:book_id>/status")
@login_required
def book_status(book_id: int):
    book = Book.query.filter_by(book_id=book_id, user_id=current_user.user_id).first()
    if not book:
        abort(404)
    chapter_count = Chapter.query.filter_by(book_id=book.book_id).count()
    return jsonify({
        "book_id":  book.book_id,
        "status":   book.processing_status,
        "chapters": chapter_count,
        "error":    book.processing_error,
        "book_url": url_for("main.book", book_id=book.book_id),
    })


@bp.get("/book/<int:book_id>")
@login_required
def book(book_id: int):
    b = Book.query.filter_by(book_id=book_id, user_id=current_user.user_id).first()
    if not b:
        abort(404)
    if b.processing_status != "ready":
        return redirect(url_for("main.processing", book_id=b.book_id))
    chapters = b.chapters.order_by(Chapter.order_index, Chapter.chapter_id).all()
    recs = Recommendation.query.filter_by(book_id=book_id, user_id=current_user.user_id).all()
    return render_template("book.html", book=b, chapters=chapters, recommendations=recs)


@bp.get("/book/<int:book_id>/chapter/<int:chapter_id>")
@login_required
def chapter(book_id: int, chapter_id: int):
    b = Book.query.filter_by(book_id=book_id, user_id=current_user.user_id).first()
    if not b:
        abort(404)
    ch = Chapter.query.filter_by(chapter_id=chapter_id, book_id=book_id).first()
    if not ch:
        abort(404)
    summ = ch.summary
    if not summ:
        abort(404)
    vocab = ch.vocabulary.order_by(Vocabulary.word).all()
    user_highlights = Highlight.query.filter_by(
        user_id=current_user.user_id, summary_id=summ.summary_id
    ).order_by(Highlight.created_at.desc()).all()
    return render_template(
        "chapter.html",
        book=b, chapter=ch, summary=summ,
        vocab=vocab, highlights=user_highlights,
    )

# NEW ROUTES
@bp.post("/api/highlights")
@login_required
def add_highlight():
    data = request.get_json(silent=True) or {}
    summary_id = data.get("summary_id")
    text = (data.get("text") or "").strip()
    color = data.get("color", "yellow")

    if not summary_id or not text:
        return jsonify({"error": "summary_id and text are required"}), 400

    summ = Summary.query.get(summary_id)
    if not summ:
        return jsonify({"error": "Summary not found"}), 404

    # Verify the summary belongs to this user's book
    chapter = Chapter.query.get(summ.chapter_id)
    book = Book.query.get(chapter.book_id)
    if book.user_id != current_user.user_id:
        abort(403)

    h = Highlight(
        user_id=current_user.user_id,
        summary_id=summary_id,
        highlighted_text=text[:2000],
        color=color,
    )
    db.session.add(h)
    db.session.commit()
    return jsonify({"highlight_id": h.highlight_id, "color": h.color}), 201


@bp.delete("/api/highlights/<int:highlight_id>")
@login_required
def delete_highlight(highlight_id: int):
    h = Highlight.query.filter_by(
        highlight_id=highlight_id, user_id=current_user.user_id
    ).first()
    if not h:
        abort(404)
    db.session.delete(h)
    db.session.commit()
    return jsonify({"deleted": True})

# NEW ROUTES — Category
@bp.post("/book/<int:book_id>/category")
@login_required
def update_category(book_id: int):
    b = Book.query.filter_by(book_id=book_id, user_id=current_user.user_id).first()
    if not b:
        abort(404)
    category_name = (request.form.get("category_name") or "").strip()[:100]
    if not category_name:
        flash("Category name cannot be empty.", "error")
        return redirect(url_for("main.book", book_id=book_id))

    if b.category:
        b.category.category_name = category_name
    else:
        db.session.add(Category(book_id=book_id, category_name=category_name))
    db.session.commit()
    flash(f"Category updated to '{category_name}'.", "success")
    return redirect(url_for("main.book", book_id=book_id))