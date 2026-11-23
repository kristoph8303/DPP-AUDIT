(function () {
  "use strict";

  const sample = "Paris is home to one of the world’s most recognized landmarks. The Eiffel Tower’s structure was completed in 1889. It opened to the public on March 31, 1889. Visitors increased by 27% in 2025.";
  const sourceText = document.getElementById("sourceText");
  const fileInput = document.getElementById("fileInput");
  const fileName = document.getElementById("fileName");
  const fileMessage = document.getElementById("fileMessage");
  const inputError = document.getElementById("inputError");
  const preview = document.getElementById("preview");
  const annotatedCopy = document.getElementById("annotatedCopy");
  const claimList = document.getElementById("claimList");
  const claimDetail = document.getElementById("claimDetail");
  const claimCount = document.getElementById("claimCount");
  const panelCount = document.getElementById("panelCount");
  const noClaims = document.getElementById("noClaims");
  const toneFeedback = document.getElementById("toneFeedback");
  let claims = [];

  const classes = {
    "Financial": "financial",
    "Statistical": "statistical",
    "Historical": "historical",
    "Scientific": "scientific",
    "Medical / Health": "medical",
    "Legal / Regulatory": "legal",
    "Technical": "technical",
    "Business / Market": "business",
    "Geographic / Demographic": "geographic",
    "Attribution": "attribution",
    "Comparative": "comparative",
    "Causal": "causal",
    "Other factual": "other"
  };

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function classify(text) {
    const value = text.toLowerCase();
    if (/[$€£]\s?\d|\b(revenue|profit|cost|price|valuation|budget|salary|worth)\b/.test(value)) return "Financial";
    if (/\b(percent|percentage|rate|average|increased by|decreased by|grew by|fell by)\b|%|\b\d+(?:\.\d+)?\s?(?:million|billion|thousand)\b/.test(value)) return "Statistical";
    if (/\b(causes?|caused|leads? to|resulted in|contributes? to|because of)\b/.test(value)) return "Causal";
    if (/\b(faster|slower|larger|smaller|higher|lower|cheaper|more than|less than|compared with|compared to)\b/.test(value)) return "Comparative";
    if (/\b(treats?|treatment|patients?|health|medical|disease|risk|mortality|clinical|medicine)\b/.test(value)) return "Medical / Health";
    if (/\b(law|legal|regulation|regulated|compliance|statute|requirement|court|rights)\b/.test(value)) return "Legal / Regulatory";
    if (/\b(software|hardware|specification|processor|algorithm|protocol|technology|technical|supports? .*version)\b/.test(value)) return "Technical";
    if (/\b(company|companies|business|market|industry|customers?|sales|shareholders?|startup)\b/.test(value)) return "Business / Market";
    if (/\b(population|residents?|located|region|city|country|geographic|demographic|kilometers?|miles)\b/.test(value)) return "Geographic / Demographic";
    if (/\b(said|stated|reported|according to|announced|wrote|testified)\b/.test(value)) return "Attribution";
    if (/\b(study|research|experiment|scientists?|scientific|measured|observed|sample size)\b/.test(value)) return "Scientific";
    if (/\b(19\d{2}|20\d{2}|18\d{2}|in \d{3,4}|on (?:january|february|march|april|may|june|july|august|september|october|november|december))\b/.test(value)) return "Historical";
    if (/\b\d+(?:\.\d+)?\b/.test(value)) return "Statistical";
    return "Other factual";
  }

  function seemsFactual(text) {
    return /\b(is|are|was|were|has|have|had|will|causes?|caused|increased|decreased|grew|fell|opened|completed|founded|invented|created|reported|measured|costs?|worth|first|largest|smallest|most|least)\b|\b\d{2,4}\b|%|[$€£]/i.test(text);
  }

  function findClaims(text) {
    const found = [];
    const lines = text.split("\n");
    let offset = 0;
    lines.forEach(function (line) {
      const rx = /[^.!?]+(?:[.!?]+|$)/g;
      let match;
      while ((match = rx.exec(line)) !== null) {
        const raw = match[0];
        const leading = raw.search(/\S/);
        if (leading < 0) continue;
        const claimText = raw.trim();
        const start = offset + match.index + leading;
        const end = start + claimText.length;
        if (claimText.split(/\s+/).length >= 5 && seemsFactual(claimText)) {
          found.push({
            id: "BC-" + String(found.length + 1).padStart(4, "0"),
            text: claimText,
            start: start,
            end: end,
            type: classify(claimText),
            status: "Needs deeper investigation"
          });
        }
      }
      offset += line.length + 1;
    });
    return found;
  }

  function typeClass(claim) {
    return "type-" + (classes[claim.type] || "other");
  }

  function renderCopy(text) {
    annotatedCopy.innerHTML = "";
    let cursor = 0;
    claims.forEach(function (claim) {
      annotatedCopy.appendChild(document.createTextNode(text.slice(cursor, claim.start)));
      const span = document.createElement("span");
      span.className = "claim-mark " + typeClass(claim);
      span.appendChild(document.createTextNode(text.slice(claim.start, claim.end)));
      const button = document.createElement("button");
      button.type = "button";
      button.className = "inline-flag";
      button.textContent = claim.id;
      button.setAttribute("aria-label", "Open " + claim.id + ", " + claim.type + " claim");
      button.setAttribute("aria-pressed", "false");
      button.dataset.claimId = claim.id;
      span.appendChild(button);
      annotatedCopy.appendChild(span);
      cursor = claim.end;
    });
    annotatedCopy.appendChild(document.createTextNode(text.slice(cursor)));
    noClaims.hidden = claims.length > 0;
  }

  function renderLedger() {
    claimList.innerHTML = "";
    claims.forEach(function (claim) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "claim-row " + typeClass(claim);
      row.dataset.claimId = claim.id;
      row.setAttribute("aria-pressed", "false");
      row.innerHTML =
        '<span class="row-top"><span class="row-id">' + escapeHtml(claim.id) +
        '</span><span class="type-tag">' + escapeHtml(claim.type) +
        '</span></span><span class="row-claim">' + escapeHtml(claim.text) +
        '</span><span class="row-bottom"><span class="status-text"><i class="status-dot-neutral"></i>' +
        escapeHtml(claim.status) + '</span></span>';
      claimList.appendChild(row);
    });
    claimCount.textContent = String(claims.length);
    panelCount.textContent = String(claims.length);
  }

  function renderDetail(claim) {
    const suggestion = "Before publication, add a reliable source that directly states this detail and have a reviewer check it. If the wording is more specific than the evidence, consider qualifying it or revising it to match the source.";
    claimDetail.innerHTML =
      '<div class="detail-heading"><div><span class="detail-id">' + escapeHtml(claim.id) +
      ' · <span class="' + typeClass(claim) + '"><span class="type-tag">' + escapeHtml(claim.type) +
      '</span></span></span><h3 id="detailTitle">A claim to review</h3></div>' +
      '<span class="neutral-status">Needs deeper investigation</span></div>' +
      '<div class="detail-grid">' +
      '<div class="detail-block"><h4>What</h4><p>“' + escapeHtml(claim.text) + '”</p></div>' +
      '<div class="detail-block"><h4>Why</h4><p>This preview identified wording that may be a factual claim. It has not checked a source, so we do not yet know whether the evidence supports, conflicts with, or simply does not address it.</p></div>' +
      '<div class="detail-block"><h4>Suggested next step</h4><p>' + escapeHtml(suggestion) + '</p></div></div>' +
      '<div class="source-note"><span aria-hidden="true">↳</span><span><strong>Evidence checked:</strong> none in this local preview. A real review should cite the relevant passage and explain whether it supports, conflicts with, or does not substantiate the wording.</span></div>';
    claimDetail.hidden = false;
    document.querySelectorAll("[data-claim-id]").forEach(function (element) {
      const selected = element.dataset.claimId === claim.id;
      element.setAttribute("aria-pressed", selected ? "true" : "false");
    });
  }

  function selectClaim(id) {
    const claim = claims.find(function (item) { return item.id === id; });
    if (claim) renderDetail(claim);
  }

  document.addEventListener("click", function (event) {
    const target = event.target.closest("[data-claim-id]");
    if (target) selectClaim(target.dataset.claimId);
  });

  document.getElementById("sampleButton").addEventListener("click", function () {
    sourceText.value = sample;
    fileName.textContent = "Sample material";
    fileMessage.textContent = "Example text loaded. It stays in this browser.";
    inputError.hidden = true;
    sourceText.focus();
  });

  fileInput.addEventListener("change", function () {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    fileName.textContent = file.name;
    if (/\.pdf$/i.test(file.name) || file.type === "application/pdf") {
      fileMessage.textContent = "PDF text extraction is not connected in this prototype. Please copy the PDF text into the box above.";
      fileInput.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = function () {
      sourceText.value = String(reader.result || "");
      fileMessage.textContent = "Text loaded locally. Nothing has been uploaded.";
      inputError.hidden = true;
    };
    reader.onerror = function () {
      fileMessage.textContent = "That file could not be read. Try pasting the text instead.";
    };
    reader.readAsText(file);
  });

  document.getElementById("previewButton").addEventListener("click", function () {
    const text = sourceText.value;
    if (!text.trim()) {
      inputError.hidden = false;
      sourceText.focus();
      return;
    }
    inputError.hidden = true;
    claims = findClaims(text);
    renderCopy(text);
    renderLedger();
    claimDetail.hidden = true;
    preview.hidden = false;
    preview.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  document.querySelectorAll(".tone-select").forEach(function (button) {
    button.addEventListener("click", function () {
      const tone = button.dataset.tone;
      document.querySelectorAll(".tone-select").forEach(function (choice) {
        const selected = choice === button;
        choice.setAttribute("aria-pressed", selected ? "true" : "false");
        choice.textContent = selected ? "Selected for later copy" : "Choose this tone";
        choice.closest(".tone-card").classList.toggle("is-selected", selected);
      });
      toneFeedback.textContent = "You chose " + tone + " for a later copy. The selected style does not change claim findings or evidence standards. This prototype does not save the choice or submit a review request.";
    });
  });
})();
