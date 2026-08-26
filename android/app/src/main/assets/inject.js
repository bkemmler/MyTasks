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

    // Token-Ablauf erkennen: 401/403 einmalig an Android melden.
    var authReported = false;
    function reportAuthRejected(status) {
        if (authReported) return;
        if (status !== 401 && status !== 403) return;
        authReported = true;
        try {
            if (window.MTAuth && window.MTAuth.expired) {
                window.MTAuth.expired(status);
            }
        } catch (e) { /* Bridge nicht verfügbar — ignorieren */ }
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
                var promise;
                if (typeof input === "string") {
                    promise = originalFetch.call(this, input, Object.assign({}, init, { headers: headers }));
                } else {
                    // Request-Objekt kann nicht mutieren → neu bauen
                    var cloned = input.clone();
                    promise = originalFetch.call(
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
                }
                return promise.then(function (response) {
                    reportAuthRejected(response.status);
                    return response;
                });
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
        this.addEventListener("load", function () {
            reportAuthRejected(this.status);
        });
        return originalOpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function () {
        if (this.__mtShouldSign && !this.getRequestHeader("P-Access-Token-Id")) {
            this.setRequestHeader("P-Access-Token-Id", window.__MT_TOKEN_ID);
            this.setRequestHeader("P-Access-Token", window.__MT_TOKEN);
        }
        return originalSend.apply(this, arguments);
    };

    // ── EventSource (SSE) ──────────────────────────────────────────
    // Native EventSource kann keine Custom-Header senden → Pangolin
    // würde 401 liefern. Für den konfigurierten Host wird daarom ein
    // fetch-basiertes Polyfill mit identischem Header-Signing genutzt.
    var OriginalEventSource = window.EventSource;
    if (OriginalEventSource) {
        window.EventSource = function (url, init) {
            if (!shouldSign(String(url))) {
                return new OriginalEventSource(url, init);
            }
            var self = this;
            self.url = String(url);
            self.readyState = 0; // CONNECTING
            self.withCredentials = !!(init && init.withCredentials);
            self._listeners = {};
            self._abort = new AbortController();
            self.onopen = null;
            self.onmessage = null;
            self.onerror = null;

            self.addEventListener = function (type, listener) {
                (self._listeners[type] = self._listeners[type] || []).push(listener);
            };
            self.removeEventListener = function (type, listener) {
                var arr = self._listeners[type];
                if (!arr) return;
                var idx = arr.indexOf(listener);
                if (idx !== -1) arr.splice(idx, 1);
            };
            self.close = function () {
                self.readyState = 2; // CLOSED
                try { self._abort.abort(); } catch (e) {}
            };
            function dispatch(type, data) {
                var event = { type: type, data: data, lastEventId: "" };
                // on<type> handler
                var handler = self["on" + type];
                if (typeof handler === "function") {
                    try { handler(event); } catch (e) {}
                }
                // addEventListener handlers
                var list = self._listeners[type];
                if (list) list.slice().forEach(function (fn) { try { fn(event); } catch (e) {} });
                // generic message handler for "message" events
                if (type !== "message" && type !== "open" && type !== "error") {
                    // custom events only via addEventListener — wie nativ
                }
            }
            // fetch mit Headern und Stream-Parsing
            fetch(url, {
                method: "GET",
                headers: {
                    "Accept": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "P-Access-Token-Id": window.__MT_TOKEN_ID,
                    "P-Access-Token": window.__MT_TOKEN
                },
                signal: self._abort.signal
            }).then(function (resp) {
                if (!resp.ok) {
                    reportAuthRejected(resp.status);
                    self.readyState = 2;
                    dispatch("error", "");
                    if (typeof self.onerror === "function") self.onerror({ type: "error" });
                    return null;
                }
                self.readyState = 1; // OPEN
                dispatch("open", "");
                if (typeof self.onopen === "function") self.onopen({ type: "open" });
                var openList = self._listeners["open"];
                if (openList) openList.slice().forEach(function (fn) { try { fn({ type: "open" }); } catch (e) {} });
                var reader = resp.body.getReader();
                var decoder = new TextDecoder();
                var buffer = "";
                var currentEvent = "message";
                var currentData = "";
                function processChunk(text) {
                    buffer += text;
                    var lines = buffer.split("\n");
                    buffer = lines.pop() || "";
                    lines.forEach(function (rawLine) {
                        var line = rawLine.replace(/\r$/, "");
                        if (line === "") {
                            if (currentData) {
                                var data = currentData.slice(0, -1); // trailing \n entfernen
                                dispatch(currentEvent, data);
                                if (currentEvent === "message" && typeof self.onmessage === "function") {
                                    try { self.onmessage({ type: "message", data: data }); } catch (e) {}
                                }
                            }
                            currentEvent = "message";
                            currentData = "";
                            return;
                        }
                        var colon = line.indexOf(":");
                        var field, value;
                        if (colon === -1) { field = line; value = ""; }
                        else { field = line.slice(0, colon); value = line.slice(colon + 1).replace(/^ /, ""); }
                        if (field === "event") currentEvent = value;
                        else if (field === "data") currentData += value + "\n";
                    });
                }
                function pump() {
                    return reader.read().then(function (result) {
                        if (result.done) { self.readyState = 2; return; }
                        processChunk(decoder.decode(result.value, { stream: true }));
                        return pump();
                    }).catch(function () { self.readyState = 2; });
                }
                return pump();
            }).catch(function (err) {
                if (err && err.name === "AbortError") return;
                self.readyState = 2;
                dispatch("error", "");
                if (typeof self.onerror === "function") try { self.onerror({ type: "error" }); } catch (e) {}
            });
            // Für instanceof-Checks
            return self;
        };
        window.EventSource.prototype = OriginalEventSource.prototype;
    }
})();
