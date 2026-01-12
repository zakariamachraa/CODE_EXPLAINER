const API_BASE = window.CODE_EXPLAINER_API || "http://localhost:8000";

const codeInput = document.getElementById("code");
const languageSelect = document.getElementById("language");
const outputPanel = document.getElementById("output");
const explainBtn = document.getElementById("explainBtn");
const themeToggle = document.getElementById("themeToggle");
const gridCanvas = document.getElementById("grid");
const ctx = gridCanvas.getContext("2d");

function resizeGrid() {
  gridCanvas.width = window.innerWidth;
  gridCanvas.height = window.innerHeight;
  drawGrid();
}

function drawGrid() {
  const spacing = 40;
  ctx.clearRect(0, 0, gridCanvas.width, gridCanvas.height);
  ctx.strokeStyle = "rgba(255,255,255,0.05)";
  for (let x = 0; x < gridCanvas.width; x += spacing) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, gridCanvas.height);
    ctx.stroke();
  }
  for (let y = 0; y < gridCanvas.height; y += spacing) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(gridCanvas.width, y);
    ctx.stroke();
  }
}

async function explain() {
  const code = codeInput.value.trim();
  if (code.length < 10) {
    renderMessage("Please provide a longer snippet.");
    return;
  }

  setLoading(true);
  try {
    const res = await fetch(`${API_BASE}/explain`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, language: languageSelect.value || null }),
    });

    if (!res.ok) throw new Error("Request failed");

    const data = await res.json();
    renderExplanation(data);
  } catch (err) {
    renderMessage("Unable to fetch explanation. Check backend status.");
  } finally {
    setLoading(false);
  }
}

function renderExplanation(payload) {
  const refs = payload.references
    .map(
      (item) => `
      <div class="reference">
        <div class="title">${item.title} (${item.language})</div>
        <p>${item.explanation}</p>
        <code>${item.code_fragment}</code>
      </div>`
    )
    .join("");

  // Line-by-line section
  const lineByLine = payload.line_by_line
    .map(
      (line) => `
      <div class="line-explanation">
        <div class="line-header">
          <span class="line-number">${line.line_number}</span>
          <code class="line-code">${escapeHtml(line.code)}</code>
        </div>
        <p class="line-desc">${line.explanation}</p>
      </div>`
    )
    .join("");

  outputPanel.innerHTML = `
    <article>
      <h2>${payload.language.toUpperCase()} Code Explanation</h2>
      <div class="summary">
        <h3>Overview</h3>
        <p>${payload.summary}</p>
      </div>
      
      <div class="reasoning">
        <h3>Analysis Steps</h3>
        <ul>
          ${payload.reasoning.map((step) => `<li>${step}</li>`).join("")}
        </ul>
      </div>
      
      <div class="line-by-line-section">
        <h3>Line-by-Line Breakdown</h3>
        <div class="line-container">
          ${lineByLine || "<p>No line-by-line analysis available.</p>"}
        </div>
      </div>
      
      <div class="references">
        <h3>Similar Code Examples</h3>
        ${refs || "<p>No references found.</p>"}
      </div>
    </article>
  `;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderMessage(message) {
  outputPanel.innerHTML = `<p class="placeholder">${message}</p>`;
}

function setLoading(state) {
  explainBtn.disabled = state;
  explainBtn.textContent = state ? "Thinking..." : "Explain";
}

function toggleTheme() {
  document.body.classList.toggle("dark");
}

window.addEventListener("resize", resizeGrid);
themeToggle.addEventListener("click", toggleTheme);
explainBtn.addEventListener("click", explain);
resizeGrid();