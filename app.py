from flask import Flask, render_template, request, send_file
from docx import Document
import requests
import os
import re
import json
from dotenv import load_dotenv

# -------------------------------------------------------
#           1) Load environment variables (.env)
# -------------------------------------------------------
load_dotenv()

# -------------------------------------------------------
#           2) Groq client init
# -------------------------------------------------------
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
try:
    groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
    if groq_client:
        print("✅ Groq Loaded Successfully")
    else:
        print("⚠️ GROQ_API_KEY missing or empty")
except Exception as e:
    print("❌ Groq Error:", e)
    groq_client = None

# -------------------------------------------------------
#           3) Flask app + LanguageTool URL
# -------------------------------------------------------
app = Flask(__name__)

LT_API_URL = "https://api.languagetool.org/v2/check"

# -------------------------------------------------------
#      4) Load Black’s Law Dictionary JSON (local)
# -------------------------------------------------------
try:
    with open("blacklaw_terms.json", "r", encoding="utf-8") as f:
        BLACKLAW = json.load(f)
except Exception:
    BLACKLAW = {}


def normalize_key(word: str) -> str:
    """Normalize keys for Black's Law lookup."""
    return re.sub(r"[^a-z\s]", "", word.lower().strip())


# -------------------------------------------------------
#      5) Legal fix rules (wrong → correct)
# -------------------------------------------------------
LEGAL_FIX = {
    "suo moto": "suo motu",
    "prima facia": "prima facie",
    "mens reaa": "mens rea",
    "ratio decedendi": "ratio decidendi",
}

# Common helper words we never want Groq to touch
IGNORE_WORDS = {
    "was", "the", "is", "and", "to", "in", "for",
    "of", "at", "by", "on", "with"
}


def is_reference_like(line: str) -> bool:
    """Lines that look like references / links -> skip grammar checks."""
    s = line.strip()
    return (
        not s
        or "http" in s
        or "www." in s
        or "doi" in s.lower()
        or re.match(r"^\[\d+\]$", s)
        or re.match(r"^\(.+\d{4}.*\)$", s)
    )


# -------------------------------------------------------
#      6) LanguageTool call (basic grammar)
# -------------------------------------------------------
def lt_check_sentence(sentence: str) -> dict:
    try:
        data = {"text": sentence, "language": "en-US"}
        r = requests.post(LT_API_URL, data=data, timeout=8)
        return r.json()
    except Exception:
        return {"matches": []}


# -------------------------------------------------------
#      7) Groq check (legal + grammar)
# -------------------------------------------------------
def groq_check(sentence: str, lt_wrong_words: list) -> list:
    """
    Groq MUST follow:
      ✓ Black’s Law Dictionary mapping
      ✓ LanguageTool-detected wrong words
      ✓ Multi-word legal terms as ONE unit
      ✓ Ignore helper words completely
    Returns: list[{"wrong": "...", "suggestion": "..."}]
    """

    # No client or nothing flagged by LT → skip Groq
    if (not groq_client) or (not lt_wrong_words):
        return []

    # Remove helper words from LT list (extra safety)
    lt_wrong_words = [
        w for w in lt_wrong_words if w.lower() not in IGNORE_WORDS
    ]
    if not lt_wrong_words:
        return []

    prompt = f"""
You are a hybrid LEGAL + GRAMMAR correction engine.

RULES (FOLLOW STRICTLY):

1. Only correct words/phrases that appear in this list from LanguageTool:
   {lt_wrong_words}

2. NEVER correct these common helper words:
   ["was", "the", "and", "is", "are", "to", "for", "of", "in", "at", "by", "on", "with"]

3. Apply Black's Law Dictionary corrections exactly:
   - "suo moto"  -> "suo motu"
   - "prima facia" -> "prima facie"
   - "ratio decedendi" -> "ratio decidendi"
   - "mens reaa" -> "mens rea"

4. Treat multi-word legal terms as ONE UNIT.
   Do NOT split or partially change them.

5. NO explanations. NO extra text.
   Output ONLY a PURE JSON array.

Example valid output:
[
  {{"wrong": "prima facia", "suggestion": "prima facie"}},
  {{"wrong": "suo moto", "suggestion": "suo motu"}}
]

Sentence to correct:
\"\"\"{sentence}\"\"\""""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",   # ✅ your available Groq model
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        raw = response.choices[0].message.content or ""

        # Extract JSON array from response
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if not match:
            return []

        return json.loads(match.group(0))

    except Exception as e:
        print("GROQ ERROR:", e)
        return []


# -------------------------------------------------------
#      8) Detect legal phrases using manual list
# -------------------------------------------------------
def detect_legal(sentence: str):
    """
    Returns list of tuples:
    [(wrong_phrase, correct_phrase, meaning), ...]
    """
    results = []

    for wrong, correct in LEGAL_FIX.items():
        if re.search(rf"\b{re.escape(wrong)}\b", sentence, re.IGNORECASE):
            meaning = BLACKLAW.get(normalize_key(correct), "")
            results.append((wrong, correct, meaning))

    return results


# -------------------------------------------------------
#      9) Build highlighted HTML line by line
# -------------------------------------------------------
def process_text_line_by_line(text: str) -> str:

    lines = text.split("\n")
    final_html = []

    for line in lines:

        # Blank line
        if not line.strip():
            final_html.append("<p></p>")
            continue

        # Reference-like line: no grammar highlight
        if is_reference_like(line):
            final_html.append(f"<p>{line}</p>")
            continue

        working = line
        html_line = line

        # ----- LanguageTool: find wrong words -----
        lt_res = lt_check_sentence(working)
        lt_wrong_words = []
        for m in lt_res.get("matches", []):
            wrong = working[m["offset"]:m["offset"] + m["length"]]
            if wrong.strip() and wrong.lower() not in IGNORE_WORDS:
                lt_wrong_words.append(wrong)

        # ----- Manual Legal detection -----
        legal_hits = detect_legal(working)

        # ----- Groq suggestions (top-level intelligence) -----
        groq_hits = groq_check(working, lt_wrong_words)

        # Combine suggestions
        combined = {}   # {wrong: {"black": ..., "groq": ...}}

        # Legal dictionary → Black suggestion
        for wrong, correct, meaning in legal_hits:
            combined.setdefault(wrong, {"black": correct, "groq": None})

        # Groq result → Groq suggestion
        for g in groq_hits:
            wrong = (g.get("wrong") or "").strip()
            suggestion = (g.get("suggestion") or "").strip()
            if not wrong or not suggestion:
                continue
            combined.setdefault(wrong, {"black": None, "groq": None})
            combined[wrong]["groq"] = suggestion

        # ----- Build HTML spans -----
        for wrong, sug in combined.items():
            black = sug["black"] or ""
            groq = sug["groq"] or ""

            span = (
                f"<span class='grammar-wrong' "
                f"data-wrong='{wrong}' "
                f"data-black='{black}' "
                f"data-groq='{groq}'>{wrong}</span>"
            )

            html_line = re.sub(
                rf"\b{re.escape(wrong)}\b",
                span,
                html_line,
                flags=re.IGNORECASE
            )

        final_html.append(f"<p>{html_line}</p>")

    return "\n".join(final_html)


# -------------------------------------------------------
#      10) Routes
# -------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        text_input = request.form.get("text", "").strip()
        file = request.files.get("file")

        if file and file.filename.endswith(".docx"):
            doc = Document(file)
            text = "\n".join([p.text for p in doc.paragraphs])
        else:
            text = text_input

        output = process_text_line_by_line(text)
        return render_template("result.html", highlighted_html=output)

    return render_template("index.html")


@app.route("/download_corrected", methods=["POST"])
def download_corrected():

    final_text = request.form.get("final_text", "")
    replacements = json.loads(request.form.get("replacements", "[]"))

    doc = Document()
    for line in final_text.split("\n"):
        doc.add_paragraph(line)

    # Apply replacements into DOCX
    for para in doc.paragraphs:
        for rep in replacements:
            wrong = rep["old"]
            correct = rep["new"]
            para.text = re.sub(
                rf"\b{re.escape(wrong)}\b",
                correct,
                para.text,
                flags=re.IGNORECASE
            )

    output_path = "static/Corrected_Final_Output.docx"
    doc.save(output_path)

    return send_file(output_path, as_attachment=True)


# -------------------------------------------------------
#      11) Run app
# -------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
