<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Grammar Check Result</title>

  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600&display=swap" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">

  <style>
    body {
      font-family: 'Poppins', sans-serif;
      background: linear-gradient(135deg, #4e54c8, #8f94fb);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 15px;
    }
    .container {
      background: #fff;
      border-radius: 16px;
      padding: 35px;
      max-width: 950px;
      width: 100%;
      box-shadow: 0 10px 25px rgba(0,0,0,0.2);
    }
    .text-area {
      border: 1px solid #ddd;
      padding: 20px;
      border-radius: 10px;
      min-height: 150px;
      white-space: pre-wrap;
    }
    .grammar-wrong, .legal-correct {
      border-bottom: 3px solid purple;
      font-weight: bold;
      cursor: pointer;
      padding: 2px 3px;
    }
    .popup-box {
      position: fixed;
      top: 25%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: white;
      padding: 20px;
      border-radius: 10px;
      width: 420px;
      box-shadow: 0 5px 20px rgba(0,0,0,0.3);
      z-index: 9999;
      display: none;
    }
    .label-title {
      font-weight: bold;
      color: #4e54c8;
    }
  </style>
</head>

<body>
  <div class="container">

    <h1>✨ Grammar Check Result</h1>

    <button class="btn btn-primary mb-3" onclick="downloadFinalDoc()">
      ⬇️ Download Corrected File (.docx)
    </button>

    <!-- MAIN TEXT -->
    <div id="textContainer" class="text-area">
      {{ highlighted_html|safe }}
    </div>

    <!-- Hidden form for sending corrected data -->
    <form id="downloadForm" action="/download_corrected" method="POST">
      <input type="hidden" name="final_text" id="finalTextField">
      <input type="hidden" name="replacements" id="finalReplacementsField">
    </form>

    <!-- POPUP BOX -->
    <div id="popup" class="popup-box">
      <h4 class="label-title">Correction Suggestion</h4>

      <p><b>Wrong Word:</b> <span id="popupWrong"></span></p>
      <p><b>Black's Law Suggestion:</b> <span id="popupBlack" style="color:green;"></span></p>
      <p><b>General Suggestion:</b> <span id="popupGeneral" style="color:#444;"></span></p>

      <button class="btn btn-success" onclick="applyFix()">Apply Fix</button>
      <button class="btn btn-warning" onclick="ignoreFix()">Ignore</button>
      <button class="btn btn-secondary" onclick="closePopup()">Cancel</button>
    </div>

  </div>

  <script>
    let selectedElement = null;
    let selectedWrong = "";
    let blackSuggestion = "";
    let generalSuggestion = "";
    let finalSuggestion = "";
    let replacements = [];

    // CLICK HANDLER
    document.addEventListener("click", function (e) {
      if (
        e.target.classList.contains("grammar-wrong") ||
        e.target.classList.contains("legal-correct")
      ) {
        selectedElement = e.target;
        selectedWrong = e.target.dataset.wrong;
        blackSuggestion = e.target.dataset.blackSuggestion || "";
        generalSuggestion = e.target.dataset.generalSuggestion || "";

        finalSuggestion = blackSuggestion || generalSuggestion;

        document.getElementById("popupWrong").innerText = selectedWrong;
        document.getElementById("popupBlack").innerText = blackSuggestion || "—";
        document.getElementById("popupGeneral").innerText =
          generalSuggestion || "—";

        document.getElementById("popup").style.display = "block";
      }
    });

    function closePopup() {
      document.getElementById("popup").style.display = "none";
    }

    // APPLY FIX
    function applyFix() {
      if (!selectedElement || !finalSuggestion) return;

      selectedElement.outerHTML =
        `<span style="background:yellow; padding:3px 5px; border-radius:4px;">${finalSuggestion}</span>`;

      replacements.push({
        old: selectedWrong,
        new: finalSuggestion,
      });

      closePopup();
    }

    // IGNORE FIX
    function ignoreFix() {
      if (!selectedElement) return;

      selectedElement.outerHTML = `<span>${selectedWrong}</span>`;
      closePopup();
    }

    // CLEAN TEXT (remove all spans + keep new lines)
    function extractCleanText() {
      const container = document.getElementById("textContainer");
      let txt = container.innerText;

      txt = txt.replace(/\s+\n/g, "\n");
      txt = txt.replace(/\n\s+/g, "\n");

      return txt.trim();
    }

    // DOWNLOAD FINAL DOCX
    function downloadFinalDoc() {
      const finalText = extractCleanText();

      document.getElementById("finalTextField").value = finalText;
      document.getElementById("finalReplacementsField").value =
        JSON.stringify(replacements);

      document.getElementById("downloadForm").submit();
    }
  </script>

</body>
</html>
