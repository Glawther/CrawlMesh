let currentJobResult = null;
let currentOutputMode = "markdown";

function switchTab(tabName) {
    document.querySelectorAll(".nav-tab").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.tab === tabName);
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === `tab-${tabName}`);
    });
}

function switchOutputView(mode) {
    currentOutputMode = mode;
    document.querySelectorAll(".subtab").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.out === mode);
    });
    renderJobOutput();
}

function setPresetUrl(url, mode) {
    document.getElementById("crawl-url").value = url;
    document.getElementById("crawl-mode").value = mode;
}

function renderJobOutput() {
    const consoleEl = document.getElementById("output-console");
    if (!currentJobResult) {
        consoleEl.textContent = "Nenhuma coleta carregada.";
        return;
    }

    if (currentOutputMode === "markdown") {
        consoleEl.textContent = currentJobResult.markdown || "(Sem conteúdo em Markdown)";
    } else if (currentOutputMode === "json") {
        const structured = {
            job_id: currentJobResult.job_id,
            url: currentJobResult.url,
            domain: currentJobResult.domain,
            http_status: currentJobResult.http_status,
            title: currentJobResult.title,
            description: currentJobResult.description,
            price_intel: currentJobResult.price_intel,
            extracted_data: currentJobResult.extracted_data,
            elapsed_ms: currentJobResult.elapsed_ms,
        };
        consoleEl.textContent = JSON.stringify(structured, null, 2);
    } else if (currentOutputMode === "links") {
        const links = currentJobResult.links || [];
        consoleEl.textContent = links.length
            ? links.map((l, i) => `[${i + 1}] ${l}`).join("\n")
            : "Nenhum link extraído.";
    }
}

function updateTelemetryPanel(job) {
    if (!job) return;
    currentJobResult = job;
    document.getElementById("tel-job-id").textContent = job.job_id;
    document.getElementById("tel-http-status").textContent = `${job.http_status || 200} ${job.status}`;
    document.getElementById("tel-latency").textContent = `${job.elapsed_ms} ms`;
    document.getElementById("tel-fingerprint").textContent = job.fingerprint_used || "Padrão";
    document.getElementById("tel-proxy").textContent = job.proxy_used || "direto";

    const badge = document.getElementById("out-price-badge");
    if (job.price_intel && job.price_intel.detected) {
        const stockTxt = job.price_intel.in_stock ? "EM ESTOQUE" : "SEM ESTOQUE";
        badge.textContent = `${job.price_intel.formatted} (${stockTxt})`;
        badge.className = "badge badge-emerald";
    } else {
        badge.textContent = `Links: ${job.links_count || 0} | Modo: ${job.mode.toUpperCase()}`;
        badge.className = "badge badge-neutral";
    }
    renderJobOutput();
}

async function submitCrawl(event) {
    event.preventDefault();
    const btn = document.getElementById("btn-run-crawl");
    const url = document.getElementById("crawl-url").value.trim();
    const mode = document.getElementById("crawl-mode").value;
    const priority = document.getElementById("crawl-priority").value;
    const rawSelectors = document.getElementById("crawl-selectors").value.trim();

    let selectors = null;
    if (rawSelectors) {
        try {
            selectors = JSON.parse(rawSelectors);
        } catch (err) {
            alert("JSON inválido no campo Seletores CSS.");
            return;
        }
    }

    btn.disabled = true;
    btn.textContent = "Extraindo...";

    try {
        const res = await fetch("/api/v1/crawl", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, mode, priority, selectors }),
        });
        const data = await res.json();
        updateTelemetryPanel(data);
        await refreshAllData();
    } catch (err) {
        console.error("Erro na coleta:", err);
    } finally {
        btn.disabled = false;
        btn.textContent = "Extrair";
    }
}

function formatBRL(val) {
    if (val === null || val === undefined) return "-";
    return Number(val).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function buildSparkline(history) {
    if (!history || !history.length) return "-";
    const prices = history.map((h) => h.price);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;
    const bars = prices.map((p, idx) => {
        const heightPct = Math.round(35 + ((p - min) / range) * 65);
        const isLast = idx === prices.length - 1 ? "last" : "";
        return `<div class="spark-bar ${isLast}" style="height:${heightPct}%" title="R$ ${p}"></div>`;
    });
    return `<div class="sparkline-pills">${bars.join("")}</div>`;
}

async function loadMonitors() {
    const res = await fetch("/api/v1/monitors");
    const monitors = await res.json();
    const tbody = document.getElementById("monitors-tbody");
    tbody.innerHTML = monitors
        .map((m) => {
            const alertBadge = m.alert_triggered
                ? `<span class="badge badge-emerald">ABAIXO DA META</span>`
                : `<span class="badge badge-amber">ACIMA DA META</span>`;
            return `
            <tr>
                <td class="mono">#${m.id}</td>
                <td>
                    <strong>${m.name}</strong>
                    <div style="font-size:11px;color:#64748b;" class="mono">${m.url}</div>
                </td>
                <td><span class="badge badge-neutral">${m.store_name}</span></td>
                <td class="mono text-emerald" style="font-weight:700;">${formatBRL(m.current_price)}</td>
                <td class="mono" style="font-size:12px;color:#94a3b8;">${formatBRL(m.lowest_price)} / ${formatBRL(m.highest_price)}</td>
                <td class="mono text-cyan">${formatBRL(m.target_price)}</td>
                <td>${buildSparkline(m.history)}</td>
                <td>${alertBadge}</td>
                <td>
                    <button class="btn-sm" onclick="checkMonitorNow(${m.id})">Atualizar agora</button>
                </td>
            </tr>
        `;
        })
        .join("");
}

async function checkMonitorNow(id) {
    await fetch(`/api/v1/monitors/${id}/check`, { method: "POST" });
    await refreshAllData();
}

function toggleNewMonitorForm() {
    document.getElementById("new-monitor-form").classList.toggle("hidden");
}

async function submitNewMonitor(event) {
    event.preventDefault();
    const payload = {
        name: document.getElementById("mon-name").value.trim(),
        url: document.getElementById("mon-url").value.trim(),
        store_name: document.getElementById("mon-store").value.trim(),
        target_price: parseFloat(document.getElementById("mon-target").value),
    };
    await fetch("/api/v1/monitors", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    document.getElementById("new-monitor-form").reset();
    document.getElementById("new-monitor-form").classList.add("hidden");
    await refreshAllData();
}

async function loadJobsAndFleet() {
    const [jobsRes, proxiesRes] = await Promise.all([
        fetch("/api/v1/jobs?limit=20"),
        fetch("/api/v1/proxies"),
    ]);
    const jobs = await jobsRes.json();
    const proxies = await proxiesRes.json();

    if (jobs.length && !currentJobResult) {
        updateTelemetryPanel(jobs[0]);
    }

    const jobsTbody = document.getElementById("jobs-tbody");
    jobsTbody.innerHTML = jobs
        .map((j) => {
            const stClass = j.status === "COMPLETED" ? "badge-emerald" : j.status === "FAILED" ? "badge-rose" : "badge-amber";
            return `
            <tr>
                <td class="mono">${j.job_id}</td>
                <td class="mono">${j.domain}</td>
                <td><span class="badge badge-neutral">${j.mode}</span></td>
                <td class="mono text-emerald">${j.http_status}</td>
                <td class="mono text-cyan">${j.elapsed_ms} ms</td>
                <td class="mono" style="font-size:11px;color:#94a3b8;">${j.fingerprint_used || "-"}</td>
                <td><span class="badge ${stClass}">${j.status}</span></td>
            </tr>
        `;
        })
        .join("");

    const proxiesTbody = document.getElementById("proxies-tbody");
    proxiesTbody.innerHTML = proxies
        .map((p) => {
            const cBadge = p.circuit_state === "CLOSED" ? "badge-emerald" : "badge-rose";
            return `
            <tr>
                <td class="mono">${p.id}</td>
                <td class="mono" style="font-size:12px;">${p.endpoint}</td>
                <td><span class="badge badge-neutral">${p.region}</span></td>
                <td class="mono text-cyan">${p.latency_ms} ms</td>
                <td class="mono">${p.success_count} / <span class="text-rose">${p.failure_count}</span></td>
                <td><span class="badge ${cBadge}">${p.circuit_state}</span></td>
            </tr>
        `;
        })
        .join("");
}

async function loadMetrics() {
    const res = await fetch("/api/v1/metrics");
    const m = await res.json();
    document.getElementById("kpi-total-jobs").textContent = m.total_jobs;
    document.getElementById("kpi-mode-label").textContent = `Modo: ${m.execution_mode} (${m.active_workers} workers)`;
    document.getElementById("kpi-success-rate").textContent = `${m.success_rate_pct}%`;
    document.getElementById("kpi-avg-latency").textContent = `${m.avg_latency_ms} ms`;
    document.getElementById("kpi-monitors").innerHTML = `${m.active_monitors} / <span class="text-amber">${m.alerts_triggered} alertas</span>`;
    document.getElementById("kpi-proxies").textContent = `${m.healthy_proxies} ativos`;
}

async function refreshAllData() {
    await Promise.all([loadMetrics(), loadMonitors(), loadJobsAndFleet()]);
}

document.addEventListener("DOMContentLoaded", () => {
    const tab = new URLSearchParams(window.location.search).get("tab");
    if (tab && ["playground", "monitors", "fleet"].includes(tab)) {
        switchTab(tab);
    }
    refreshAllData();
});
