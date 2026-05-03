(() => {
  function detectDOI() {
    const metas = [
      'meta[name="citation_doi"]',
      'meta[name="DC.identifier"]',
      'meta[name="dc.identifier"]',
      'meta[name="doi"]',
      'meta[scheme="doi"]',
      'meta[property="citation_doi"]',
    ];
    for (const sel of metas) {
      const el = document.querySelector(sel);
      if (el) {
        const v = el.getAttribute("content") || "";
        const m = v.match(/(10\.\d{4,}\/[^\s]+)/);
        if (m) return m[1];
      }
    }

    const urlMatch = window.location.href.match(/doi\.org\/(10\.\d{4,}\/[^\s&?#]+)/);
    if (urlMatch) return urlMatch[1];

    const hrefMatch = window.location.href.match(/\/(10\.\d{4,}\/[^\s&?#]+)/);
    if (hrefMatch) return hrefMatch[1];

    const links = document.querySelectorAll('a[href*="doi.org/10."]');
    for (const a of links) {
      const m = a.href.match(/doi\.org\/(10\.\d{4,}\/[^\s&?#]+)/);
      if (m) return m[1];
    }

    return null;
  }

  function detectPDFUrl() {
    const meta = document.querySelector('meta[name="citation_pdf_url"]');
    if (meta) return meta.getAttribute("content");

    const links = document.querySelectorAll('a[href]');
    for (const a of links) {
      const href = a.getAttribute("href") || "";
      const text = (a.textContent || "").toLowerCase();
      if (href.match(/\.pdf(\?|$|#)/i) || text.includes("pdf")) {
        try {
          return new URL(href, window.location.origin).href;
        } catch { /* skip */ }
      }
    }
    return null;
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.type === "DETECT") {
      sendResponse({
        doi: detectDOI(),
        pdfUrl: detectPDFUrl(),
        pageUrl: window.location.href,
      });
    }
    return true;
  });
})();
