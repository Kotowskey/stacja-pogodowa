(() => {
    "use strict";

    const STALE_AFTER_MS = 60_000; // 1 min bez pomiaru => węzeł "offline"

    const state = {
        nodes: new Map(),        // node_id -> { id, name, lastMeasurement, lastSeen }
        selectedNode: null,
        rangeLimit: 100,
        charts: { temp: null, pres: null, hum: null },
    };

    // -------------------------------------------------------------------- helpers
    const $ = (sel) => document.querySelector(sel);
    const fmt = (val, digits = 1) =>
        (val === null || val === undefined || Number.isNaN(val)) ? "—" : Number(val).toFixed(digits);
    const fmtTime = (iso) => {
        if (!iso) return "—";
        const d = new Date(iso);
        return d.toLocaleTimeString("pl-PL") + " · " + d.toLocaleDateString("pl-PL");
    };

    function ensureNode(id, name) {
        if (!state.nodes.has(id)) {
            state.nodes.set(id, {
                id,
                name: name || id,
                lastMeasurement: null,
                lastSeen: null,
            });
        }
        return state.nodes.get(id);
    }

    // ---------------------------------------------------------------------- UI: cards
    function renderCards() {
        const wrap = $("#cards");
        wrap.innerHTML = "";

        if (state.nodes.size === 0) {
            wrap.innerHTML = `<div class="empty">Brak węzłów. Uruchom symulator lub podłącz ESP32.</div>`;
            return;
        }

        const now = Date.now();
        for (const node of state.nodes.values()) {
            const m = node.lastMeasurement;
            const fresh = node.lastSeen && (now - new Date(node.lastSeen).getTime()) < STALE_AFTER_MS;

            const el = document.createElement("article");
            el.className = "card";
            el.innerHTML = `
                <div class="card__head">
                    <div>
                        <div class="card__name">${escapeHtml(node.name)}</div>
                        <div class="card__id">${escapeHtml(node.id)}</div>
                    </div>
                    <div class="card__status">
                        <span class="dot ${fresh ? "dot--on" : "dot--off"}"></span>
                        ${fresh ? "online" : "offline"}
                    </div>
                </div>
                <div class="metrics">
                    <div class="metric metric--temp">
                        <div class="metric__label">Temperatura</div>
                        <div class="metric__value">${fmt(m?.temperature)}<span class="metric__unit"> °C</span></div>
                    </div>
                    <div class="metric metric--pres">
                        <div class="metric__label">Ciśnienie</div>
                        <div class="metric__value">${fmt(m?.pressure)}<span class="metric__unit"> hPa</span></div>
                    </div>
                    <div class="metric metric--hum">
                        <div class="metric__label">Wilgotność</div>
                        <div class="metric__value">${fmt(m?.humidity)}<span class="metric__unit"> %</span></div>
                    </div>
                </div>
                <div class="card__ts">Ostatni pomiar: ${fmtTime(m?.timestamp)}</div>
            `;
            wrap.appendChild(el);
        }
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
        })[c]);
    }

    // ---------------------------------------------------------- UI: node selector
    function renderNodeOptions() {
        const sel = $("#node-select");
        const previous = sel.value;
        sel.innerHTML = "";

        if (state.nodes.size === 0) {
            const opt = document.createElement("option");
            opt.value = ""; opt.textContent = "(brak węzłów)";
            sel.appendChild(opt);
            return;
        }

        for (const node of state.nodes.values()) {
            const opt = document.createElement("option");
            opt.value = node.id;
            opt.textContent = `${node.name} (${node.id})`;
            sel.appendChild(opt);
        }

        if (previous && state.nodes.has(previous)) {
            sel.value = previous;
        } else if (!state.selectedNode || !state.nodes.has(state.selectedNode)) {
            state.selectedNode = sel.value;
        }
        sel.value = state.selectedNode;
    }

    // -------------------------------------------------------------------- charts
    function makeChart(canvasId, label, color) {
        const ctx = document.getElementById(canvasId).getContext("2d");
        return new Chart(ctx, {
            type: "line",
            data: {
                datasets: [{
                    label,
                    data: [],
                    borderColor: color,
                    backgroundColor: color + "22",
                    borderWidth: 2,
                    tension: .3,
                    pointRadius: 0,
                    fill: true,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { intersect: false, mode: "index" },
                plugins: {
                    legend: { labels: { color: "#e6edf6" } },
                    tooltip: { mode: "index", intersect: false },
                },
                scales: {
                    x: {
                        type: "time",
                        time: { tooltipFormat: "yyyy-MM-dd HH:mm:ss" },
                        ticks: { color: "#8aa0c2", maxRotation: 0, autoSkip: true },
                        grid: { color: "rgba(255,255,255,.05)" },
                    },
                    y: {
                        ticks: { color: "#8aa0c2" },
                        grid: { color: "rgba(255,255,255,.05)" },
                    },
                },
            },
        });
    }

    function initCharts() {
        state.charts.temp = makeChart("chart-temp", "Temperatura [°C]", "#ff9d6c");
        state.charts.pres = makeChart("chart-pres", "Ciśnienie [hPa]", "#c1a4ff");
        state.charts.hum  = makeChart("chart-hum",  "Wilgotność [%]", "#6cd3ff");
    }

    function setHistory(measurements) {
        const xy = (key) => measurements.map((m) => ({ x: m.timestamp, y: m[key] }));
        state.charts.temp.data.datasets[0].data = xy("temperature");
        state.charts.pres.data.datasets[0].data = xy("pressure");
        state.charts.hum.data.datasets[0].data  = xy("humidity");
        for (const c of Object.values(state.charts)) c.update("none");
    }

    function appendLive(m) {
        if (!state.selectedNode || m.node_id !== state.selectedNode) return;
        const push = (chart, val) => {
            const ds = chart.data.datasets[0].data;
            ds.push({ x: m.timestamp, y: val });
            if (ds.length > state.rangeLimit) ds.shift();
            chart.update("none");
        };
        push(state.charts.temp, m.temperature);
        push(state.charts.pres, m.pressure);
        push(state.charts.hum,  m.humidity);
    }

    // ---------------------------------------------------------------------- API
    async function fetchJson(url) {
        const r = await fetch(url);
        if (!r.ok) throw new Error(`${url} -> HTTP ${r.status}`);
        return r.json();
    }

    async function loadNodes() {
        const data = await fetchJson("/api/nodes");
        for (const n of data) {
            const node = ensureNode(n.id, n.name);
            if (n.last_measurement) node.lastMeasurement = n.last_measurement;
            if (n.last_seen) node.lastSeen = n.last_seen;
        }
        // dorzuć węzły z konfiguracji (jeśli API ich nie zwróciło)
        for (const n of (window.__INITIAL_NODES__ || [])) ensureNode(n.id, n.name);

        renderCards();
        renderNodeOptions();
    }

    async function loadHistory() {
        if (!state.selectedNode) return;
        const url = `/api/measurements/history?node_id=${encodeURIComponent(state.selectedNode)}&limit=${state.rangeLimit}`;
        const data = await fetchJson(url);
        setHistory(data);
    }

    // ---------------------------------------------------------------- WebSocket
    function connectWs() {
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(`${proto}//${location.host}/ws`);

        const dot = $("#conn-dot");
        const txt = $("#conn-text");

        ws.addEventListener("open", () => {
            dot.classList.remove("dot--off"); dot.classList.add("dot--on");
            txt.textContent = "podłączono";
        });
        ws.addEventListener("close", () => {
            dot.classList.remove("dot--on"); dot.classList.add("dot--off");
            txt.textContent = "rozłączono - próba ponownego połączenia...";
            setTimeout(connectWs, 1500);
        });
        ws.addEventListener("error", () => ws.close());
        ws.addEventListener("message", (ev) => {
            try {
                const msg = JSON.parse(ev.data);
                if (msg.type === "measurement") onMeasurement(msg.data);
            } catch (_) { /* ignore */ }
        });
    }

    function onMeasurement(m) {
        const node = ensureNode(m.node_id, m.node_id);
        node.lastMeasurement = m;
        node.lastSeen = m.timestamp;
        renderCards();
        renderNodeOptions();
        appendLive(m);
    }

    // ---------------------------------------------------------------------- init
    function bindControls() {
        $("#node-select").addEventListener("change", (e) => {
            state.selectedNode = e.target.value;
            loadHistory().catch(console.error);
        });
        $("#range-select").addEventListener("change", (e) => {
            state.rangeLimit = parseInt(e.target.value, 10) || 100;
            loadHistory().catch(console.error);
        });
        setInterval(renderCards, 5_000); // odświeżanie statusu online/offline
    }

    async function init() {
        for (const n of (window.__INITIAL_NODES__ || [])) ensureNode(n.id, n.name);
        renderCards();
        renderNodeOptions();
        initCharts();
        bindControls();

        try {
            await loadNodes();
            await loadHistory();
        } catch (e) {
            console.error("Init error:", e);
        }
        connectWs();
    }

    document.addEventListener("DOMContentLoaded", init);
})();
