import re
import logging
from pathlib import Path
from typing import List, Tuple
import pdfplumber

logging.getLogger("pdfminer").setLevel(logging.ERROR)


def extract_text_from_pdf(path: Path) -> str:
    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            parts.append(t.strip())
    return "\n\n".join(parts)


def _find_toc_end(lines: list) -> int:
    """
    Find where the TOC ends by looking for the FIRST real chapter heading
    that is followed by actual body text (not just more headings).
    Much more conservative than before.
    """
    toc_header = re.compile(r"^(contents|table of contents)$", re.IGNORECASE)
    chapter_pat = re.compile(r"^(?:chapter|ch\.?)\s+(\d+|[ivxlcdm]+)\b", re.IGNORECASE)

    # Only look for TOC header in first 60 lines
    toc_start = -1
    for i, line in enumerate(lines[:60]):
        if toc_header.match(line.strip()):
            toc_start = i
            print(f"[pdf_service] TOC header found at line {i}")
            break

    if toc_start == -1:
        print("[pdf_service] No TOC header found — not skipping any lines")
        return 0

    # Scan forward from TOC header to find where chapter listings end
    # The TOC ends when we hit a blank-line gap followed by real prose
    # a line longer than 80 chars that isn't a chapter reference
    last_chapter_ref = toc_start
    for i in range(toc_start + 1, min(toc_start + 150, len(lines))):
        s = lines[i].strip()
        if chapter_pat.match(s):
            last_chapter_ref = i

    # The actual first chapter in the BODY starts after the last TOC entry
    # We return last_chapter_ref so detection starts FROM there,
    # meaning the first real "Chapter 1" heading is included
    toc_end = last_chapter_ref + 1
    print(f"[pdf_service] TOC ends at line {toc_end} (last ref at {last_chapter_ref})")
    return toc_end


def detect_chapters(full_text: str) -> List[Tuple[str, str]]:
    lines = full_text.splitlines()

    # Skip TOC
    body_start = _find_toc_end(lines)
    working_lines = lines[body_start:]
    print(f"[pdf_service] Skipping {body_start} TOC lines. Working with {len(working_lines)} lines.")

    # Patterns
    pat_chapter   = re.compile(r"^(?:chapter|ch\.?)\s+(\d+|[ivxlcdm]+)\b", re.IGNORECASE)
    pat_bare_num  = re.compile(r"^\d{1,3}$")
    pat_num_title = re.compile(r"^\d{1,3}[.\-:]\s+\S")
    pat_allcaps   = re.compile(r"^[A-Z][A-Z\s\-]{3,50}$")
    pat_titlecase = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,6}$")

    def find_breaks(pat, min_matches=2, sequential=False):
        breaks = []
        expected = 1
        for i, line in enumerate(working_lines):
            s = line.strip()
            if not s:
                continue
            if pat.match(s):
                if sequential:
                    try:
                        num = int(s)
                        if num == expected:
                            breaks.append((i, s))
                            expected += 1
                    except ValueError:
                        pass
                else:
                    breaks.append((i, s))
        return breaks if len(breaks) >= min_matches else []

    breaks = (
        find_breaks(pat_chapter,   min_matches=2) or
        find_breaks(pat_bare_num,  min_matches=2, sequential=True) or
        find_breaks(pat_num_title, min_matches=2) or
        find_breaks(pat_allcaps,   min_matches=2) or
        find_breaks(pat_titlecase, min_matches=3)
    )

    print(f"[pdf_service] Found {len(breaks)} chapter breaks")

    # Fallback
    if not breaks:
        print("[pdf_service] No pattern matched — word chunking fallback")
        words = full_text.split()
        chunk = 1500
        return [
            (f"Section {(i//chunk)+1}", " ".join(words[i:i+chunk]))
            for i in range(0, len(words), chunk)
        ]

    # Build chapters
    out = []

    pre = "\n".join(working_lines[: breaks[0][0]]).strip()
    if len(pre.split()) > 50:
        out.append(("Introduction", pre))

    for j, (start_line, raw_title) in enumerate(breaks):
        end_line = breaks[j + 1][0] if j + 1 < len(breaks) else len(working_lines)
        body = "\n".join(working_lines[start_line + 1: end_line]).strip()

        # FIXED: minimum 5 words, not 15
        if len(body.split()) < 5:
            print(f"[pdf_service] Skipping '{raw_title}' — body too short ({len(body.split())} words)")
            continue

        if re.match(r"^\d+$", raw_title.strip()):
            clean_title = f"Chapter {raw_title.strip()}"
        else:
            clean_title = re.sub(r"^\d+[.\-:\s]+", "", raw_title).strip() or raw_title

        out.append((clean_title, body))

    if not out:
        print("[pdf_service] No valid chapters — chunking fallback")
        words = full_text.split()
        chunk = 1500
        return [
            (f"Section {(i//chunk)+1}", " ".join(words[i:i+chunk]))
            for i in range(0, len(words), chunk)
        ]

    print(f"[pdf_service] Returning {len(out)} chapters")
    return out