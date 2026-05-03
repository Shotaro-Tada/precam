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

  function buildPublisherPdfUrl(doi) {
    const host = window.location.hostname;
    const path = window.location.pathname;

    if (host.includes("sciencedirect.com") || host.includes("elsevier.com")) {
      for (const a of document.querySelectorAll('a[href*="pdfft"], a[href*="/pdf"]')) {
        const href = a.getAttribute("href") || "";
        if (/pdfft|\/pdf\?/.test(href)) {
          try { return new URL(href, window.location.origin).href; } catch { /* skip */ }
        }
      }
      const piiMatch = path.match(/\/pii\/([A-Z0-9]+)/i);
      if (piiMatch) return `https://www.sciencedirect.com/science/article/pii/${piiMatch[1]}/pdfft?download=true`;
    }
    if (!doi) return null;
    if (host.includes("wiley.com")) {
      return `https://${host}/doi/pdfdirect/${doi}?download=true`;
    }
    if (host.includes("acs.org")) {
      return `https://pubs.acs.org/doi/pdf/${doi}`;
    }
    if (host.includes("nature.com") || host.includes("springer.com")) {
      return `https://link.springer.com/content/pdf/${doi}.pdf`;
    }
    if (host.includes("rsc.org")) {
      return `https://pubs.rsc.org/en/content/articlepdf/${new Date().getFullYear()}/xx/${doi}`;
    }
    if (host.includes("tandfonline.com")) {
      return `https://www.tandfonline.com/doi/pdf/${doi}?download=true`;
    }
    if (host.includes("mdpi.com")) {
      const meta = document.querySelector('meta[name="citation_pdf_url"]');
      if (meta) return meta.getAttribute("content");
    }
    return null;
  }

  function detectPDFUrl() {
    if (/\.pdf(\?|$|#)/i.test(window.location.href)) {
      return window.location.href;
    }

    const doi = detectDOI();
    const pubUrl = buildPublisherPdfUrl(doi);
    if (pubUrl) return pubUrl;

    const meta = document.querySelector('meta[name="citation_pdf_url"]');
    if (meta) {
      const url = meta.getAttribute("content");
      if (url && /\.pdf(\?|$|#)/i.test(url)) {
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
