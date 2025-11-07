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
    Highlights incorrect words in red and suggestions in green.
    Avoids overlap and multiple replacements.
    """
    for para in doc.paragraphs:
        text = para.text
        if not text.strip():
            continue

        # Collect valid matches with positions and suggestions
        errors = []
        for match in matches:
            context = match.get("context", {})
            offset = context.get("offset")
            length = context.get("length")
            replacements = match.get("replacements", [])
            suggestion = replacements[0]["value"] if replacements else None

            if (
                suggestion
                and isinstance(offset, int)
                and isinstance(length, int)
                and offset + length <= len(text)
            ):
                errors.append((offset, length, suggestion))

        # Sort descending by offset to avoid shifting positions
        errors.sort(reverse=True, key=lambda x: x[0])

        for offset, length, suggestion in errors:
            wrong = text[offset:offset + length]
            replacement = f"[{wrong} → {suggestion}]"
            text = text[:offset] + replacement + text[offset + length:]

        para.text = text

        # Apply formatting (red for wrong, green for correct)
        new_runs = []
        for part in para.text.split("["):
            if "→" in part and "]" in part:
                wrong_part = part.split("→")[0].strip()
                suggestion_part = part.split("→")[1].split("]")[0].strip()

                red_run = (wrong_part, RGBColor(255, 0, 0), True, False)
                green_run = (suggestion_part, RGBColor(0, 128, 0), False, True)
                new_runs.append(red_run)
                new_runs.append((" ", None, False, False))
                new_runs.append(green_run)
            else:
                new_runs.append((part, None, False, False))

        # Clear old paragraph
        for run in para.runs:
            run.text = ""
        para.text = ""

        # Add formatted runs
        for text_part, color, bold, italic in new_runs:
            run = para.add_run(text_part)
            if color:
                run.font.color.rgb = color
            run.bold = bold
            run.italic = italic

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

    # Save output as _corrected.docx
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
