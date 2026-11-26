(function () {
  "use strict";

  const sample = "Paris is home to one of the world’s most recognized landmarks. The Eiffel Tower’s structure was completed in 1889. It opened to the public on March 31, 1889. Visitors increased by 27% in 2025.";
  const source = document.getElementById("operatorSource");
  const fileInput = document.getElementById("operatorFile");
  const fileName = document.getElementById("operatorFileName");
  const claimList = document.getElementById("operatorClaimList");
  const operatorCopy = document.getElementById("operatorCopy");
  const operatorDetail = document.getElementById("operatorDetail");
  const claimCount = document.getElementById("operatorClaimCount");
  const progress = document.getElementById("reviewProgress");
  const pageBook = document.getElementById("pageBook");
  const dropZone = document.getElementById("operatorDropZone");
  let extracted = [];
  let activeClaimId = null;

  const classNames = {
    "Financial / Economic": "financial",
    "Statistical": "statistical",
    "Historical": "historical",
    "Scientific / Technical": "scientific",
    "Health / Medical": "health",
    "Legal / Regulatory": "legal",
    "Product / Performance": "product",
    "Attribution / Quotation": "attribution",
    "General Factual": "general",
    "Other Verifiable": "other"
  };

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function classify(text) {
    const value = text.toLowerCase();
    if (/[$€£]\s?\d|\b(revenue|profit|cost|price|valuation|budget|salary|worth|economic|inflation|gdp)\b/.test(value)) return "Financial / Economic";
    if (/\b(percent|percentage|rate|average|increased by|decreased by|grew by|fell by)\b|%|\b\d+(?:\.\d+)?\s?(?:million|billion|thousand)\b/.test(value)) return "Statistical";
    if (/\b(treats?|treatment|patients?|health|medical|disease|risk|mortality|clinical|medicine|symptom|diagnosis)\b/.test(value)) return "Health / Medical";
    if (/\b(law|legal|regulation|regulated|compliance|statute|requirement|court|rights)\b/.test(value)) return "Legal / Regulatory";
    if (/\b(software|hardware|specification|processor|algorithm|protocol|technology|technical|study|research|experiment|scientists?|scientific|measured|observed|sample size)\b/.test(value)) return "Scientific / Technical";
    if (/\b(product|device|model|performance|battery|speed|durability|efficiency|faster|slower|larger|smaller|higher|lower|cheaper|compared with|compared to)\b/.test(value)) return "Product / Performance";
    if (/\b(said|stated|reported|according to|announced|wrote|testified|quote|quoted|quotation)\b/.test(value)) return "Attribution / Quotation";
    if (/\b(19\d{2}|20\d{2}|18\d{2}|in \d{3,4}|on (?:january|february|march|april|may|june|july|august|september|october|november|december))\b/.test(value)) return "Historical";
    if (/\b\d+(?:\.\d+)?\b/.test(value)) return "Statistical";
    if (/\b(is|are|was|were|has|have|had|will|causes?|caused|leads? to|resulted in|contributes? to|because of|located|contains?|includes?)\b/i.test(value)) return "General Factual";
    return "Other Verifiable";
  }

  function seemsFactual(text) {
    return /\b(is|are|was|were|has|have|had|will|causes?|caused|increased|decreased|grew|fell|opened|completed|founded|invented|created|reported|measured|costs?|worth|first|largest|smallest|most|least)\b|\b\d{2,4}\b|%|[$€£]/i.test(text);
  }

  function typeClass(claim) {
    return "type-" + (classNames[claim.type] || "other");
  }

  function extractCandidates(text) {
    const found = [];
    let offset = 0;
    text.split("\n").forEach(function (line) {
      const expression = /[^.!?]+(?:[.!?]+|$)/g;
      let match;
      while ((match = expression.exec(line)) !== null) {
        const raw = match[0];
        const leading = raw.search(/\S/);
        if (leading < 0) continue;
        const claimText = raw.trim();
        const start = offset + match.index + leading;
        if (claimText.split(/\s+/).length >= 5 && seemsFactual(claimText)) {
          found.push({
            id: "BC-" + String(found.length + 1).padStart(4, "0"),
            text: claimText,
            start: start,
            end: start + claimText.length,
            type: classify(claimText),
            reviewed: false
          });
        }
      }
      offset += line.length + 1;
    });
    return found;
  }

  function renderOriginal(text) {
    operatorCopy.innerHTML = "";
    if (!text) {
      operatorCopy.innerHTML = '<p class="empty-state">Load or paste material, then choose Extract claims.</p>';
      return;
    }
    let cursor = 0;
    extracted.forEach(function (claim) {
      operatorCopy.appendChild(document.createTextNode(text.slice(cursor, claim.start)));
      const span = document.createElement("span");
      span.className = "claim-mark " + typeClass(claim) + (activeClaimId === claim.id ? " is-selected" : "");
      span.appendChild(document.createTextNode(text.slice(claim.start, claim.end)));
      const flag = document.createElement("button");
      flag.type = "button";
      flag.className = "inline-flag";
      flag.textContent = String(foundIndex(claim) + 1);
      flag.dataset.claimId = claim.id;
      flag.setAttribute("aria-label", "Open claim " + String(foundIndex(claim) + 1));
      flag.setAttribute("aria-pressed", activeClaimId === claim.id ? "true" : "false");
      span.appendChild(flag);
      operatorCopy.appendChild(span);
      cursor = claim.end;
    });
    operatorCopy.appendChild(document.createTextNode(text.slice(cursor)));
  }

  function foundIndex(claim) {
    return extracted.findIndex(function (item) { return item.id === claim.id; });
  }

  function renderList() {
    claimList.innerHTML = "";
    if (!extracted.length) {
      claimList.innerHTML = '<p class="empty-state" style="padding:14px">No candidate claims found by the local pattern scan. It may miss claims.</p>';
      claimCount.textContent = "0";
      progress.textContent = "0 / 0 checked";
      return;
    }
    extracted.forEach(function (claim, index) {
      const row = document.createElement("div");
      row.className = "operator-claim-row " + typeClass(claim) + (claim.reviewed ? " is-reviewed" : "") + (activeClaimId === claim.id ? " is-selected" : "");
      row.innerHTML =
        '<span class="operator-claim-number">' + String(index + 1).padStart(2, "0") + '</span>' +
        '<button class="operator-claim-open" type="button" data-claim-id="' + escapeHtml(claim.id) + '" aria-pressed="false">' +
        '<span class="operator-claim-copy">' + escapeHtml(claim.text) +
        '<span class="operator-claim-type">' + escapeHtml(claim.type) + '</span></span></button>' +
        '<label aria-label="Mark claim ' + String(index + 1) + ' reviewed"><input class="operator-check" type="checkbox" data-review-id="' + escapeHtml(claim.id) + '"' + (claim.reviewed ? " checked" : "") + '></label>';
      claimList.appendChild(row);
    });
    claimCount.textContent = String(extracted.length);
    updateProgress();
  }

  function updateProgress() {
    const done = extracted.filter(function (claim) { return claim.reviewed; }).length;
    progress.textContent = done + " / " + extracted.length + " checked";
  }

  function renderDetail(claim) {
    activeClaimId = claim.id;
    operatorDetail.innerHTML =
      '<div class="operator-detail-heading"><div><span class="operator-detail-id">' + escapeHtml(claim.id) + ' · ' + escapeHtml(claim.type) +
      '</span><h4>Claim ' + String(foundIndex(claim) + 1).padStart(2, "0") + '</h4></div><span class="neutral-status">Not assessed</span></div>' +
      '<div class="operator-detail-grid">' +
      '<div class="operator-detail-block"><h5>What</h5><p>“' + escapeHtml(claim.text) + '”</p></div>' +
      '<div class="operator-detail-block"><h5>Why</h5><p>The local scan identified a possible factual statement. No source has been searched or checked.</p></div>' +
      '<div class="operator-detail-block"><h5>Evidence</h5><p>None in this prototype. Add the exact source passage during a real review.</p></div>' +
      '<div class="operator-detail-block"><h5>Suggested correction</h5><p>No factual correction is suggested before checking evidence. After the sources are assessed, revise only wording that they do not support, and explain the change.</p></div></div>';
    operatorDetail.hidden = false;
    document.querySelectorAll(".operator-claim-row").forEach(function (row) {
      row.classList.toggle("is-selected", row.querySelector("[data-claim-id]")?.dataset.claimId === claim.id);
    });
    document.querySelectorAll(".operator-claim-open, .operator-copy [data-claim-id]").forEach(function (item) {
      const selected = item.dataset.claimId === claim.id;
      item.setAttribute("aria-pressed", selected ? "true" : "false");
      const marker = item.closest(".claim-mark");
      if (marker) marker.classList.toggle("is-selected", selected);
    });
  }

  function showPage(pageId) {
    const current = document.querySelector(".work-page:not([hidden])");
    const next = document.getElementById(pageId);
    if (!current || !next || current === next) return;
    if (pageBook.classList.contains("is-turning")) return;
    pageBook.classList.add("is-turning");
    window.setTimeout(function () {
      current.hidden = true;
      next.hidden = false;
      document.querySelectorAll(".page-tab").forEach(function (tab) {
        const active = tab.dataset.page === pageId;
        tab.classList.toggle("is-active", active);
        tab.setAttribute("aria-pressed", active ? "true" : "false");
      });
      window.requestAnimationFrame(function () { pageBook.classList.remove("is-turning"); });
    }, 210);
  }

  document.querySelectorAll(".page-tab").forEach(function (tab) {
    tab.addEventListener("click", function () { showPage(tab.dataset.page); });
  });

  document.getElementById("generateTopics").addEventListener("click", function () {
    const topic = document.getElementById("topicInput").value.trim();
    const suggestions = document.getElementById("topicSuggestions");
    suggestions.innerHTML = "";
    if (!topic) {
      suggestions.innerHTML = "<li>Enter a topic first.</li>";
      return;
    }
    [
      "What precise factual statements are being made about " + topic + "?",
      "Which primary or official sources directly address " + topic + "?",
      "Which independent sources could confirm or qualify those statements?"
    ].forEach(function (suggestion) {
      const item = document.createElement("li");
      item.textContent = suggestion;
      suggestions.appendChild(item);
    });
  });

  document.getElementById("loadExample").addEventListener("click", function () {
    source.value = sample;
    fileName.textContent = "Eiffel Tower sample text";
  });

  fileInput.addEventListener("change", function () {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    fileName.textContent = file.name;
    if (!/\.(txt|md|csv)$/i.test(file.name)) {
      source.value = "";
      fileName.textContent = file.name + " — prototype reads TXT, MD, CSV only";
      return;
    }
    const reader = new FileReader();
    reader.onload = function () { source.value = String(reader.result || ""); };
    reader.readAsText(file);
  });

  ["dragenter", "dragover"].forEach(function (eventName) {
    dropZone.addEventListener(eventName, function (event) {
      event.preventDefault();
      dropZone.classList.add("is-dragging");
    });
  });
  ["dragleave", "dragend", "drop"].forEach(function (eventName) {
    dropZone.addEventListener(eventName, function (event) {
      event.preventDefault();
      dropZone.classList.remove("is-dragging");
    });
  });
  dropZone.addEventListener("drop", function (event) {
    const file = event.dataTransfer.files && event.dataTransfer.files[0];
    if (!file) return;
    fileName.textContent = file.name;
    if (!/\.(txt|md|csv)$/i.test(file.name)) {
      source.value = "";
      fileName.textContent = file.name + " — prototype reads TXT, MD, CSV only";
      return;
    }
    const reader = new FileReader();
    reader.onload = function () { source.value = String(reader.result || ""); };
    reader.readAsText(file);
  });

  document.getElementById("extractClaims").addEventListener("click", function () {
    extracted = extractCandidates(source.value);
    activeClaimId = null;
    renderOriginal(source.value);
    renderList();
    operatorDetail.hidden = true;
  });

  document.addEventListener("click", function (event) {
    const target = event.target.closest("[data-claim-id]");
    if (!target || target.matches("[data-review-id]")) return;
    const claim = extracted.find(function (item) { return item.id === target.dataset.claimId; });
    if (claim) renderDetail(claim);
  });

  document.addEventListener("change", function (event) {
    const checkbox = event.target.closest("[data-review-id]");
    if (!checkbox) return;
    const claim = extracted.find(function (item) { return item.id === checkbox.dataset.reviewId; });
    if (!claim) return;
    claim.reviewed = checkbox.checked;
    checkbox.closest(".operator-claim-row").classList.toggle("is-reviewed", claim.reviewed);
    updateProgress();
  });
})();
