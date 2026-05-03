const $ = (sel) => document.querySelector(sel);

let paperData = null;
let pdfUrl = null;

function generateId() {
  const hex = "0123456789abcdef";
  let id = "";
  for (let i = 0; i < 12; i++) id += hex[Math.floor(Math.random() * 16)];
  return id;
}

function generateBibtexKey(paper) {
  const family = (paper.authors[0]?.family || "unknown").toLowerCase().replace(/[^a-z]/g, "");
  const year = paper.year || "";
  const keyword = (paper.title || "")
    .split(/\s+/)
    .find((w) => w.length > 3 && !["with", "from", "that", "this", "were", "been", "have"].includes(w.toLowerCase()));
  return `${family}${year}${(keyword || "").toLowerCase().replace(/[^a-z]/g, "")}`;
}

function isoNow() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function showMsg(text, type) {
  const el = $("#msg");
  el.textContent = text;
  el.className = `status ${type}`;
  el.hidden = false;
  setTimeout(() => (el.hidden = true), 4000);
}

async function loadSettings() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(
      { libraries: { "PreCAM-Shotaro": ["General"] } },
      resolve
    );
  });
}

async function saveSettings(settings) {
  return new Promise((resolve) => {
    chrome.storage.sync.set(settings, resolve);
  });
}

function populateLibraries(settings) {
  const libSel = $("#library-select");
  const prev = libSel.value;
  libSel.innerHTML = "";
  for (const name of Object.keys(settings.libraries)) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    libSel.appendChild(opt);
  }
  if (prev && settings.libraries[prev]) libSel.value = prev;
  populateFolders(settings);
}

function populateFolders(settings) {
  const lib = $("#library-select").value;
  const folders = settings.libraries[lib] || [];
  const datalist = $("#folder-list");
  datalist.innerHTML = "";
  for (const f of folders) {
    const opt = document.createElement("option");
    opt.value = f;
    datalist.appendChild(opt);
  }
}

async function rememberFolder(lib, folder) {
  if (!folder) return;
  const settings = await loadSettings();
  if (!settings.libraries[lib]) settings.libraries[lib] = [];
  if (!settings.libraries[lib].includes(folder)) {
    settings.libraries[lib].push(folder);
    settings.libraries[lib].sort();
    await saveSettings(settings);
    populateFolders(settings);
  }
}

function displayPaper(paper) {
  $("#p-doi").textContent = paper.doi;
  $("#p-title").textContent = paper.title;
  $("#p-authors").textContent = paper.authors
    .map((a) => `${a.given} ${a.family}`)
    .join(", ");
  $("#p-journal").textContent =
    [paper.journal, paper.volume, paper.issue ? `(${paper.issue})` : "", paper.pages]
      .filter(Boolean)
      .join(", ") || "-";
  $("#p-year").textContent = paper.year || "-";
  paperData = paper;
}

async function fetchAndDisplay(doi) {
  $("#loading").textContent = "Fetching metadata...";
  $("#loading").hidden = false;

  const resp = await chrome.runtime.sendMessage({ type: "FETCH_CROSSREF", doi });
  $("#loading").hidden = true;

  if (!resp?.ok) {
    showMsg(`CrossRef error: ${resp?.error || "unknown"}`, "error");
    $("#no-doi").hidden = false;
    return;
  }

  displayPaper(resp.paper);
  const settings = await loadSettings();
  populateLibraries(settings);
  $("#paper-info").hidden = false;
}

document.addEventListener("DOMContentLoaded", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const tabUrl = tab?.url || "";

  const isDirectPdf = /\.pdf(\?|$|#)/i.test(tabUrl) || tab?.title?.endsWith(".pdf");

  if (isDirectPdf) {
    pdfUrl = tabUrl;
  }

  try {
    const detection = await chrome.tabs.sendMessage(tab.id, { type: "DETECT" });
    if (detection?.pdfUrl && !isDirectPdf) pdfUrl = detection.pdfUrl;

    if (detection?.doi) {
      await fetchAndDisplay(detection.doi);
    } else {
      const doiFromUrl = tabUrl.match(/doi\.org\/(10\.\d{4,}\/[^\s&?#]+)/);
      if (doiFromUrl) {
        await fetchAndDisplay(doiFromUrl[1]);
      } else {
        $("#loading").hidden = true;
        $("#no-doi").hidden = false;
      }
    }
  } catch {
    const doiFromUrl = tabUrl.match(/doi\.org\/(10\.\d{4,}\/[^\s&?#]+)/);
    if (doiFromUrl) {
      await fetchAndDisplay(doiFromUrl[1]);
    } else {
      $("#loading").hidden = true;
      $("#no-doi").hidden = false;
    }
  }

  $("#save-pdf").disabled = !pdfUrl;

  $("#library-select").addEventListener("change", async () => {
    const settings = await loadSettings();
    populateFolders(settings);
    $("#folder-input").value = "";
  });

  $("#sync-litman").addEventListener("click", async () => {
    try {
      const resp = await fetch("http://localhost:51780/api/folders");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const settings = await loadSettings();
      for (const [lib, folders] of Object.entries(data)) {
        if (lib === "_other") continue;
        if (!settings.libraries[lib]) settings.libraries[lib] = [];
        for (const f of folders) {
          if (!settings.libraries[lib].includes(f)) {
            settings.libraries[lib].push(f);
          }
        }
        settings.libraries[lib].sort();
      }
      await saveSettings(settings);
      populateLibraries(settings);
      showMsg("Synced from litman!", "success");
    } catch {
      showMsg("litman not running", "error");
    }
  });

  $("#manual-fetch").addEventListener("click", async () => {
    const doi = $("#manual-doi").value.trim();
    if (!doi) return;
    $("#no-doi").hidden = true;
    await fetchAndDisplay(doi);
  });

  $("#save-litman").addEventListener("click", async () => {
    if (!paperData) return;

    const library = $("#library-select").value;
    const folder = $("#folder-input").value.trim();

    if (!folder) {
      showMsg("Please enter a folder name", "error");
      return;
    }

    await rememberFolder(library, folder);

    const now = isoNow();
    const paper = {
      abstract: paperData.abstract || null,
      added_at: now,
      arxiv_id: null,
      authors: paperData.authors,
      bibtex_key: generateBibtexKey(paperData),
      doi: paperData.doi || null,
      id: generateId(),
      issue: paperData.issue || null,
      journal: paperData.journal || null,
      journal_abbrev: paperData.journalAbbrev || null,
      notes: "",
      pages: paperData.pages || null,
      publisher: paperData.publisher || null,
      tags: [folder ? `folder:${library}/${folder}` : `folder:${library}`],
      title: paperData.title,
      updated_at: now,
      url: `https://doi.org/${paperData.doi}`,
      volume: paperData.volume || null,
      year: paperData.year || null,
    };

    try {
      const resp = await fetch("http://localhost:51780/api/papers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(paper),
      });
      const result = await resp.json();
      if (resp.status === 201) {
        showMsg("Saved to litman!", "success");
      } else if (resp.status === 409) {
        showMsg(`Already exists: ${result.title?.substring(0, 50)}...`, "error");
      } else {
        showMsg(`Error: ${result.error}`, "error");
      }
    } catch {
      showMsg("litman not running", "error");
    }
  });

  $("#save-pdf").addEventListener("click", () => {
    if (!pdfUrl) {
      showMsg("No PDF URL detected", "error");
      return;
    }

    const library = $("#library-select").value;
    const folder = $("#folder-input").value.trim() || "General";
    let filename = "paper.pdf";
    if (paperData) {
      const family = (paperData.authors[0]?.family || "unknown").replace(/[^a-zA-Z0-9]/g, "");
      const year = paperData.year || "";
      const title = (paperData.title || "").replace(/:/g, "_").replace(/[<>"/\\|?*]/g, "").trim();
      filename = `${family}-${year}-${title}.pdf`;
    }

    chrome.downloads.download(
      { url: pdfUrl, filename, saveAs: true },
      (downloadId) => {
        if (chrome.runtime.lastError) {
          showMsg(`Error: ${chrome.runtime.lastError.message}`, "error");
        } else {
          showMsg("PDF saved!", "success");
        }
      }
    );
  });

  $("#open-options").addEventListener("click", (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
  });
});
