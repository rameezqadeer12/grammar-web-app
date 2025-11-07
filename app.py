from flask import Flask, render_template, request, send_file, url_for
from docx import Document
from docx.shared import RGBColor
import requests
import io
import os
import re

app = Flask(__name__)

LT_API_URL = "https://api.languagetool.org/v2/check"


# -----------------------------
# Helper: detect reference-like lines
# -----------------------------
def is_reference_like(line: str) -> bool:
    line_strip = line.strip()
    if not line_strip:
        return True
    # URLs / DOIs
    if "http" in line_strip or "www." in line_strip or "doi" in line_strip.lower():
        return True
    # [1], [12]
    if re.match(r"^\[\d+\]$", line_strip):
        return True
    # (Kim et al., 2024)
    if re.match(r"^\(.+\d{4}.*\)$", line_strip):
        return True
    return False


# -----------------------------
# Helper: call LanguageTool
# -----------------------------
def lt_check_sentence(sentence: str, lang="en-US"):
    data = {"text": sentence, "language": lang}
    resp = requests.post(LT_API_URL, data=data)
    resp.raise_for_status()
    return resp.json()


# -----------------------------
# DOCX highlighting (for download)
# This one checks EACH paragraph separately,
# so the downloaded file matches what you see on web.
# -----------------------------
def highlight_docx_paragraphs(doc: Document) -> Document:
    for para in doc.paragraphs:
        original_text = para.text
        if not original_text.strip():
            continue

        # skip references / links
        if is_reference_like(original_text):
            continue

        # run LT on this paragraph only
        result = lt_check_sentence(original_text)
        matches = result.get("matches", [])
        if not matches:
            continue

        # collect spans
        spans = []
        for m in matches:
            offset = m.get("offset")
            length = m.get("length")
            replacements = m.get("replacements", [])
            suggestion = replacements[0]["value"] if replacements else ""
            if offset is None or length is None:
                continue
            spans.append((offset, length, suggestion))

        # sort by offset ascending so we can rebuild text
        spans.sort(key=lambda x: x[0])

        # rebuild paragraph text into colored runs
        new_segments = []
        cursor = 0
        for offset, length, suggestion in spans:
            start = offset
            end = offset + length
            # normal text before error
            if cursor < start:
                new_segments.append((original_text[cursor:start], None, False))
            wrong_word = original_text[start:end]
            # wrong in red + bold
            new_segments.append((wrong_word, RGBColor(255, 0, 0), True))
            # suggestion in green (if any)
            if suggestion:
                new_segments.append((" → " + suggestion, RGBColor(0, 128, 0), False))
            cursor = end

        # remaining text
        if cursor < len(original_text):
            new_segments.append((original_text[cursor:], None, False))

        # clear old paragraph
        for r in para.runs:
            r.text = ""
        para.text = ""

        # write back with formatting
        for text_part, color, bold in new_segments:
            run = para.add_run(text_part)
            if color:
                run.font.color.rgb = color
            run.bold = bold

    return doc


# -----------------------------
# Web preview builder (you already had this)
# -----------------------------
def process_text_line_by_line(text: str):
    lines = text.splitlines()
    final_html_parts = []
    all_issues = []
    line_no = 0

    for line in lines:
        line_no += 1

        # skip refs
        if is_reference_like(line):
            final_html_parts.append(f"<p>{line}</p>")
            continue

        if not line.strip():
            final_html_parts.append("<p></p>")
            continue

        lt_result = lt_check_sentence(line)
        matches = lt_result.get("matches", [])
        spans = []
        for m in matches:
            offset = m.get("offset")
            length = m.get("length")
            replacements = m.get("replacements", [])
            suggestion = replacements[0]["value"] if replacements else None
            message = m.get("message", "")
            if offset is None or length is None:
                continue
            spans.append({
                "offset": offset,
                "length": length,
                "suggestion": suggestion,
                "message": message
            })

        # sort by offset
        spans.sort(key=lambda x: x["offset"])

        html_line = ""
        cursor = 0
        for sp in spans:
            start = sp["offset"]
            end = sp["offset"] + sp["length"]
            wrong = line[start:end]
            before = line[cursor:start]
            html_line += before
            html_line += (
                f"<span class='error' data-suggestion='{sp['suggestion'] or ''}' "
                f"data-message='{sp['message']}'>{wrong}</span>"
            )

            all_issues.append({
                "line": line_no,
                "wrong": wrong,
                "suggestion": sp["suggestion"] or "",
                "message": sp["message"]
            })
            cursor = end

        html_line += line[cursor:]
        final_html_parts.append(f"<p>{html_line}</p>")

    highlighted_html = "\n".join(final_html_parts)
    return highlighted_html, all_issues


# -----------------------------
# Routes
# -----------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        input_text = request.form.get("text", "").strip()
        file = request.files.get("file")

        # 1) get text + doc object
        if file and file.filename.endswith(".docx"):
            doc = Document(file)
            text = "\n".join([p.text for p in doc.paragraphs])
            original_name = os.path.splitext(file.filename)[0]
        else:
            text = input_text
            doc = Document()
            doc.add_paragraph(text)
            original_name = "corrected_output"

        if not text:
            return render_template("index.html", error="Please provide text or upload a .docx file.")

        # 2) build web preview
        highlighted_html, issues = process_text_line_by_line(text)

        # 3) build downloadable docx (paragraph-wise)
        highlighted_doc = highlight_docx_paragraphs(doc)

        # 4) save to static
        os.makedirs("static", exist_ok=True)
        filename = f"{original_name}_corrected.docx"
        output_path = os.path.join("static", filename)
        highlighted_doc.save(output_path)

        # 5) render page
        return render_template(
            "result.html",
            highlighted_html=highlighted_html,
            issues=issues,
            download_link=url_for("download_file", filename=filename)
        )

    return render_template("index.html")


@app.route("/download/<filename>")
def download_file(filename):
    file_path = os.path.join("static", filename)
    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
