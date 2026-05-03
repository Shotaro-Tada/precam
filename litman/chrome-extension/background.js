function cleanAbstract(raw) {
  if (!raw) return null;
  let text = raw;
  text = text.replace(/<jats:sup>([^<]*)<\/jats:sup>/gi, "^$1");
  text = text.replace(/<sup>([^<]*)<\/sup>/gi, "^$1");
  text = text.replace(/<jats:sub>([^<]*)<\/jats:sub>/gi, "$1");
  text = text.replace(/<sub>([^<]*)<\/sub>/gi, "$1");
  text = text.replace(/<jats:italic>([^<]*)<\/jats:italic>/gi, "$1");
  text = text.replace(/<italic>([^<]*)<\/italic>/gi, "$1");
  text = text.replace(/<jats:p>/gi, " ");
  text = text.replace(/<\/jats:p>/gi, " ");
  text = text.replace(/<[^>]*>/g, "");
  text = text.replace(/\s+/g, " ").trim();
  return text;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "FETCH_CROSSREF") {
    fetch(`https://api.crossref.org/works/${encodeURIComponent(msg.doi)}`, {
      headers: { "User-Agent": "litman-chrome-extension/1.0 (mailto:shotaro.tada.m@gmail.com)" },
    })
      .then((r) => r.json())
      .then((data) => {
        const w = data.message;
        const authors = (w.author || []).map((a) => ({
          given: a.given || "",
          family: a.family || "",
        }));
        const year =
          w.published?.["date-parts"]?.[0]?.[0] ||
          w["published-print"]?.["date-parts"]?.[0]?.[0] ||
          w["published-online"]?.["date-parts"]?.[0]?.[0] ||
          null;
        const title = Array.isArray(w.title) ? w.title[0] || "" : w.title || "";
        const journal = (w["container-title"] || [])[0] || null;
        const journalAbbrev = (w["short-container-title"] || [])[0] || null;
        const volume = w.volume || null;
        const issue = w.issue || null;
        const pages = w.page || null;
        const publisher = w.publisher || null;
        const abstract = cleanAbstract(w.abstract);

        sendResponse({
          ok: true,
          paper: { title, authors, year, journal, journalAbbrev, volume, issue, pages, publisher, abstract, doi: msg.doi },
        });
      })
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }
});
