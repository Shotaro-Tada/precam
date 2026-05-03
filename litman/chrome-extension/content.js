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
    if (/\.pdf(\?|$|#)/i.test(window.location.href)) {
      return window.location.href;
    }

    const meta = document.querySelector('meta[name="citation_pdf_url"]');
    if (meta) {
      const url = meta.getAttribute("content");
      if (url) {
        try { return new URL(url, window.location.origin).href; } catch { /* skip */ }
      }
    }

    const links = document.querySelectorAll('a[href]');
    for (const a of links) {
      const href = a.getAttribute("href") || "";
      if (/\.pdf(\?|$|#)/i.test(href)) {
        try { return new URL(href, window.location.origin).href; } catch { /* skip */ }
      }
    }

    for (const a of links) {
      const href = a.getAttribute("href") || "";
      const text = (a.textContent || "").trim().toLowerCase();
      if ((text === "pdf" || text === "download pdf") && href && !href.startsWith("javascript:")) {
        try { return new URL(href, window.location.origin).href; } catch { /* skip */ }
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
