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
      // URL pattern: /en/content/articlelanding/YYYY/XX/ID → articlepdf/YYYY/XX/ID
      const rscMatch = path.match(/\/content\/articlelanding\/([\d]{4}\/[a-z]{2}\/[a-z0-9]+)/i);
      if (rscMatch) return `https://pubs.rsc.org/en/content/articlepdf/${rscMatch[1]}`;
      // Fallback: try citation_pdf_url meta tag
      const rscMeta = document.querySelector('meta[name="citation_pdf_url"]');
      if (rscMeta) return rscMeta.getAttribute("content");
      return null;
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

  // ScienceDirect / Elsevier serve `…/pdfft?download=true` as a short HTML
  // interstitial ("your download will begin shortly") that JS-redirects to a
  // signed pdf.sciencedirectassets.com link. Handing the pdfft URL straight to
  // chrome.downloads therefore saves the .html, not the PDF. Running here in the
  // page origin lets us fetch it WITH the session cookies, follow the redirect,
  // and hand back the real PDF URL.
  async function resolveElsevierPdf(pdfUrl) {
    try {
      const resp = await fetch(pdfUrl, { credentials: "include" });
      const ctype = (resp.headers.get("content-type") || "").toLowerCase();
      // Redirect already followed: the final URL points at the PDF asset.
      if (ctype.includes("application/pdf")) {
        return resp.url || pdfUrl;
      }
      const html = await resp.text();
      // Common interstitial shapes: meta refresh, a JS location assignment, or
      // an anchor to the asset host.
      const patterns = [
        /content=["']\s*\d+\s*;\s*url=([^"']+)["']/i,
        /window\.location(?:\.href)?\s*=\s*["']([^"']+)["']/i,
        /href=["'](https:\/\/pdf\.sciencedirectassets\.com\/[^"']+)["']/i,
        /["'](https:\/\/pdf\.sciencedirectassets\.com\/[^"']+)["']/i,
      ];
      for (const re of patterns) {
        const m = html.match(re);
        if (m && m[1]) {
          try { return new URL(m[1].replace(/&amp;/g, "&"), resp.url || pdfUrl).href; }
          catch { /* skip */ }
        }
      }
      return resp.url || pdfUrl;
    } catch {
      return pdfUrl; // network/CORS failure: fall back to the original URL
    }
  }

  function getPageMeta() {
    const ogTitle = document.querySelector('meta[property="og:title"]');
    const ogDesc = document.querySelector('meta[property="og:description"]');
    const ogSite = document.querySelector('meta[property="og:site_name"]');
    const metaDesc = document.querySelector('meta[name="description"]');
    return {
      title: (ogTitle?.content || document.title || "").trim(),
      description: (ogDesc?.content || metaDesc?.content || "").trim(),
      siteName: (ogSite?.content || "").trim(),
    };
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.type === "DETECT") {
      sendResponse({
        doi: detectDOI(),
        pdfUrl: detectPDFUrl(),
        pageUrl: window.location.href,
        pageMeta: getPageMeta(),
      });
      return true;
    }
    if (msg.type === "RESOLVE_PDF") {
      resolveElsevierPdf(msg.pdfUrl).then((url) => sendResponse({ url }));
      return true; // keep the message channel open for the async reply
    }
    return true;
  });
})();
