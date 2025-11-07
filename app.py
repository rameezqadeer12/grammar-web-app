from flask import Flask, render_template, request, send_file
from docx import Document
from docx.shared import RGBColor
import requests
import io
import os

app = Flask(__name__)

LT_API_URL = "https://api.languagetool.org/v2/check"

def check_grammar(text, lang="en-US"):
    """Send text to LanguageTool API."""
    data = {"text": text, "language": lang}
    resp = requests.post(LT_API_URL, data=data)
    resp.raise_for_status()
    return resp.json()

def highlight_incorrect_words(doc, matches):
    """
    Highlights incorrect word(s) in red and their suggestions in green.
    Avoids multiple replacements or nested brackets.
    """
    for para in doc.paragraphs:
        text = para.text
        errors = []

        for match in matches:
            offset = match["context"]["offset"]
            length = match["context"]["length"]
            replacements = match.get("replacements", [])
            suggestion = replacements[0]["value"] if replacements else None

            if not suggestion or offset < 0 or length <= 0:
                continue
            errors.append((offset, length, suggestion))

        # Sort by offset descending to avoid corruption when replacing
        errors.sort(reverse=True)
        for offset, length, suggestion in errors:
            wrong = text[offset:offset + length]
            # Insert formatted text
            text = text[:offset] + f"[{wrong} → {suggestion}]" + text[offset + length:]

        para.text = text

        # Apply color formatting
        for run in para.runs:
            if "→" in run.text:
                parts = run.text.split("→")
                if len(parts) == 2:
                    wrong_part, suggestion_part = parts
                    run.clear()
                    red_run = para.add_run(wrong_part)
                    red_run.font.color.rgb = RGBColor(255, 0, 0)
                    red_run.bold = True

                    arrow_run = para.add_run("→")

                    green_run = para.add_run(suggestion_part)
                    green_run.font.color.rgb = RGBColor(0, 128, 0)
                    green_run.italic = True
    return doc


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or not file.filename.endswith(".docx"):
        return "Please upload a .docx file", 400

    original_filename = os.path.splitext(file.filename)[0]

    doc = Document(file)
    full_text = "\n".join([p.text for p in doc.paragraphs])

    lt_result = check_grammar(full_text, lang="en-US")
    matches = lt_result.get("matches", [])

    highlighted_doc = highlight_incorrect_words(doc, matches)

    output_filename = f"{original_filename}_corrected.docx"
    output = io.BytesIO()
    highlighted_doc.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=output_filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
