// Schicht 3: P-Access-Token-Header für alle fetch()- und XMLHttpRequest-Calls.
// Die Tokens werden von MainActivity als globale Variablen injiziert:
//   window.__MT_TOKEN_ID / window.__MT_TOKEN
// Nur Requests an den konfigurierten Host (window.__MT_HOST) werden versehen.
(function () {
    "use strict";

    var HOST = window.__MT_HOST;
    if (!HOST) return;

    function shouldSign(url) {
        try {
            return new URL(url, window.location.href).host === HOST;
        } catch (e) {
            return false;
        }
    }

    // ── fetch ────────────────────────────────────────────────────────
    var originalFetch = window.fetch;
    if (originalFetch) {
        window.fetch = function (input, init) {
            try {
                var url = typeof input === "string"
                    ? input
                    : (input && input.url) || "";
                if (!shouldSign(url)) {
                    return originalFetch.apply(this, arguments);
                }
                init = init || {};
                var headers = new Headers(init.headers || (input && input.headers) || {});
                if (!headers.has("P-Access-Token-Id")) {
                    headers.set("P-Access-Token-Id", window.__MT_TOKEN_ID);
                    headers.set("P-Access-Token", window.__MT_TOKEN);
                }
                if (typeof input === "string") {
                    return originalFetch.call(this, input, Object.assign({}, init, { headers: headers }));
                }
                // Request-Objekt kann nicht mutieren → neu bauen
                var cloned = input.clone();
                return originalFetch.call(
                    this,
                    new Request(cloned.url, {
                        method: cloned.method,
                        headers: headers,
                        body: ["GET", "HEAD"].indexOf(cloned.method) === -1 ? cloned.body : undefined,
                        mode: cloned.mode,
                        credentials: cloned.credentials,
                        cache: cloned.cache,
                        redirect: cloned.redirect,
                        referrer: cloned.referrer,
                        integrity: cloned.integrity,
                    }),
                    init
                );
            } catch (e) {
                return originalFetch.apply(this, arguments);
            }
        };
    }

    // ── XMLHttpRequest ───────────────────────────────────────────────
    var originalOpen = XMLHttpRequest.prototype.open;
    var originalSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url) {
        this.__mtUrl = url;
        this.__mtShouldSign = shouldSign(String(url));
        return originalOpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function () {
        if (this.__mtShouldSign && !this.getRequestHeader("P-Access-Token-Id")) {
            this.setRequestHeader("P-Access-Token-Id", window.__MT_TOKEN_ID);
            this.setRequestHeader("P-Access-Token", window.__MT_TOKEN);
        }
        return originalSend.apply(this, arguments);
    };
})();
