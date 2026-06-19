(() => {
    const THEME_KEY = "repoHubTheme";
    const PLACEHOLDERS = [
        "vercel/next.js",
        "fastapi/fastapi",
        "https://github.com/django/django",
        "git@github.com:pallets/flask.git"
    ];

    const state = {
        current: null,
        currentRepo: "",
        auth: null,
        history: [],
        pipelineRuns: [],
        setupRepos: [],
        activeTab: "overview",
        mode: "single",
        moduleDone: new Set(),
        activeBatchRepo: "",
        batchResults: [],
        renderers: {
            home: null,
            globe: null,
            health: null,
            deps: null
        }
    };

    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatNumber(value) {
        const num = Number(value);
        if (!Number.isFinite(num)) return "0";
        return num.toLocaleString();
    }

    function compactNumber(value) {
        const num = Number(value);
        if (!Number.isFinite(num)) return "0";
        return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(num);
    }

    function clamp(value, min = 0, max = 100) {
        const num = Number(value);
        if (!Number.isFinite(num)) return min;
        return Math.max(min, Math.min(max, num));
    }

    function normalizeRepoSlug(value) {
        let slug = String(value || "").trim();
        if (!slug) return "";

        if (slug.startsWith("git@github.com:")) {
            slug = slug.replace("git@github.com:", "");
        } else if (slug.startsWith("ssh://git@github.com/")) {
            slug = slug.replace("ssh://git@github.com/", "");
        } else if (/^https?:\/\//i.test(slug)) {
            try {
                const url = new URL(slug);
                if (url.hostname.replace(/^www\./, "").toLowerCase() !== "github.com") return "";
                slug = url.pathname.replace(/^\/+|\/+$/g, "");
            } catch (error) {
                return "";
            }
        } else {
            slug = slug.replace(/^(www\.)?github\.com\//i, "");
        }

        slug = slug.split("?")[0].split("#")[0].replace(/\.git$/i, "").replace(/^\/+|\/+$/g, "");
        const parts = slug.split("/");
        if (parts.length < 2) return "";
        const owner = parts[0];
        const repo = parts[1];
        if (!/^[A-Za-z0-9_.-]+$/.test(owner) || !/^[A-Za-z0-9_.-]+$/.test(repo)) return "";
        return `${owner}/${repo}`;
    }

    function getRepoFromData(data = state.current) {
        return normalizeRepoSlug(data?.repo || data?.metadata?.full_name || data?.cicd?.slug || data?.dependencies?.repository || state.currentRepo);
    }

    function showToast(message, type = "info", duration = 3600) {
        const stack = $("#toast-stack");
        if (!stack) return;
        const normalizedMessage = String(message || "")
            .replace(/\s+/g, " ")
            .trim();
        const displayMessage = normalizedMessage.length > 220
            ? `${normalizedMessage.slice(0, 217)}...`
            : normalizedMessage;
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span class="toast-marker" aria-hidden="true"></span>
            <div>${escapeHtml(displayMessage)}</div>
            <button type="button" aria-label="Dismiss toast">x</button>
        `;
        toast.querySelector("button").addEventListener("click", () => toast.remove());
        stack.appendChild(toast);
        if (duration > 0) {
            setTimeout(() => {
                toast.style.opacity = "0";
                toast.style.transform = "translateY(10px)";
                setTimeout(() => toast.remove(), 220);
            }, duration);
        }
    }

    function setInputError(message = "") {
        const el = $("#input-error");
        if (!el) return;
        el.textContent = message;
        el.classList.toggle("active", Boolean(message));
    }

    async function copyText(text, label = "Copied") {
        try {
            await navigator.clipboard.writeText(text);
            showToast(label, "success", 2200);
        } catch (error) {
            showToast("Clipboard copy failed", "error");
        }
    }

    function applyTheme(theme, persist = true) {
        const next = theme === "light" ? "light" : "dark";
        document.documentElement.dataset.theme = next;
        if (persist) {
            try { localStorage.setItem(THEME_KEY, next); } catch (error) {}
        }
        const icon = $("#theme-icon");
        if (icon) icon.textContent = next === "dark" ? "D" : "L";
        const landingIcon = $("#landing-theme-icon");
        if (landingIcon) landingIcon.textContent = next === "dark" ? "D" : "L";
    }

    function initTheme() {
        let theme = "dark";
        try { theme = localStorage.getItem(THEME_KEY) || document.documentElement.dataset.theme || "dark"; } catch (error) {}
        applyTheme(theme, false);
        $("#theme-toggle")?.addEventListener("click", () => {
            const current = document.documentElement.dataset.theme === "light" ? "light" : "dark";
            const next = current === "dark" ? "light" : "dark";
            applyTheme(next);
            showToast(`${next === "dark" ? "Dark" : "Light"} theme enabled`, "success", 2000);
        });
        $("#landing-theme-toggle")?.addEventListener("click", () => {
            const current = document.documentElement.dataset.theme === "light" ? "light" : "dark";
            const next = current === "dark" ? "light" : "dark";
            applyTheme(next);
            showToast(`${next === "dark" ? "Dark" : "Light"} theme enabled`, "success", 2000);
        });
    }

    function initTypewriter() {
        const input = $("#repo-input");
        if (!input) return;
        let phrase = 0;
        let index = 0;
        let deleting = false;

        function tick() {
            if (document.activeElement === input || input.value) {
                setTimeout(tick, 900);
                return;
            }
            const text = PLACEHOLDERS[phrase];
            index += deleting ? -1 : 1;
            input.placeholder = text.slice(0, Math.max(0, index));
            if (!deleting && index >= text.length) {
                deleting = true;
                setTimeout(tick, 1400);
                return;
            }
            if (deleting && index <= 0) {
                deleting = false;
                phrase = (phrase + 1) % PLACEHOLDERS.length;
            }
            setTimeout(tick, deleting ? 42 : 78);
        }
        tick();
    }

    function showLanding() {
        const landing = $("#landing-page");
        const dashboard = $("#dashboard-app");
        if (landing) landing.hidden = false;
        if (dashboard) dashboard.hidden = true;
        document.body.classList.add("landing-active");
        document.body.classList.remove("dashboard-active");
        disposeRenderer("home");
        requestAnimationFrame(() => {
            initHomeScene();
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    }

    function enterDashboard({ focusInput = false, updateHash = true } = {}) {
        const landing = $("#landing-page");
        const dashboard = $("#dashboard-app");
        if (landing) landing.hidden = true;
        if (dashboard) dashboard.hidden = false;
        document.body.classList.remove("landing-active");
        document.body.classList.add("dashboard-active");
        disposeRenderer("home");
        const tab = tabFromHash();
        if (updateHash && !tab && window.location.hash !== "#dashboard") {
            history.pushState(null, "", "#dashboard");
        }
        requestAnimationFrame(() => {
            window.scrollTo({ top: 0, behavior: "auto" });
            if (focusInput) $("#repo-input")?.focus({ preventScroll: true });
            const activeTab = tabFromHash();
            if (activeTab) switchTab(activeTab, false);
        });
    }

    function tabFromHash() {
        const value = (window.location.hash || "").replace(/^#/, "");
        if (value === "dashboard" || value === "analysis") return "overview";
        const allowed = new Set(["overview", "cicd", "deps", "pipeline", "setup", "history"]);
        return allowed.has(value) ? value : "";
    }

    function canOpenDashboard() {
        const auth = state.auth;
        if (!auth) return false;
        return Boolean(auth.authenticated || !auth.require_login);
    }

    function requestDashboardEntry() {
        if (canOpenDashboard()) {
            enterDashboard({ focusInput: true });
            return;
        }
        if (state.auth?.github_login_configured) {
            window.location.href = "/api/auth/login";
            return;
        }
        showToast("GitHub sign up is not configured for this local server.", "warning", 5200);
        $("#landing-auth-card")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    function requestGithubSignup() {
        if (state.auth?.authenticated) {
            enterDashboard({ focusInput: true });
            return;
        }
        if (state.auth?.github_login_configured) {
            window.location.href = "/api/auth/login";
            return;
        }
        showToast("Add GitHub App OAuth credentials in .env, then restart the server.", "warning", 6200);
        $("#landing-auth-card")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    function initLandingReveal() {
        const revealItems = $$(".landing-section, .landing-final");
        if (!revealItems.length) return;
        if (!("IntersectionObserver" in window)) {
            revealItems.forEach(item => item.classList.add("is-visible"));
            return;
        }
        const observer = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;
                entry.target.classList.add("is-visible");
                observer.unobserve(entry.target);
            });
        }, { rootMargin: "0px 0px -12% 0px", threshold: 0.12 });
        revealItems.forEach(item => observer.observe(item));
    }

    function initLanding() {
        $$("[data-enter-dashboard]").forEach(button => {
            button.addEventListener("click", requestDashboardEntry);
        });
        $$("[data-auth-login]").forEach(button => {
            button.addEventListener("click", requestGithubSignup);
        });
        $$(".landing-links a[href^='#'], .landing-brand[href^='#']").forEach(link => {
            link.addEventListener("click", event => {
                const target = $(link.getAttribute("href"));
                if (!target) return;
                event.preventDefault();
                history.pushState(null, "", link.getAttribute("href"));
                target.scrollIntoView({ behavior: "smooth", block: "start" });
            });
        });
        initLandingReveal();
        if (window.location.hash === "#dashboard" || window.location.hash === "#analysis" || tabFromHash()) {
            enterDashboard({ updateHash: false });
        } else {
            $("#landing-page")?.removeAttribute("hidden");
            $("#dashboard-app")?.setAttribute("hidden", "");
            document.body.classList.add("landing-active");
            document.body.classList.remove("dashboard-active");
            initHomeScene();
            const target = window.location.hash ? $(window.location.hash) : null;
            if (target) {
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => target.scrollIntoView({ behavior: "auto", block: "start" }));
                });
            }
        }
        window.addEventListener("popstate", () => {
            if (window.location.hash === "#dashboard" || window.location.hash === "#analysis" || tabFromHash()) {
                enterDashboard({ updateHash: false });
            } else {
                showLanding();
            }
        });
    }

    function switchTab(tab, scroll = false) {
        state.activeTab = tab;
        $$(".nav-item, .tab-btn, .mobile-tab").forEach(btn => {
            btn.classList.toggle("active", btn.dataset.tab === tab);
        });
        $$(".tab-panel").forEach(panel => {
            panel.classList.toggle("active", panel.id === `tab-${tab}`);
        });
        $("#results-shell")?.classList.add("active");
        if (tab === "history") renderHistory();
        if (tab === "pipeline") loadPipelineRuns();
        if (tab === "setup") loadSetupRepositories();
        if (scroll) $("#results-shell")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function initTabs() {
        document.addEventListener("click", event => {
            const tabButton = event.target.closest("[data-tab]");
            if (!tabButton) return;
            const tab = tabButton.dataset.tab;
            if (!tab) return;
            event.preventDefault();
            switchTab(tab, true);
        });

        $$(".mode-tab").forEach(btn => {
            btn.addEventListener("click", () => {
                state.mode = btn.dataset.mode || "single";
                $$(".mode-tab").forEach(item => item.classList.toggle("active", item === btn));
                $$(".analysis-mode-panel").forEach(panel => panel.classList.remove("active"));
                $(`#${state.mode}-panel`)?.classList.add("active");
            });
        });
    }

    function setMarketingVisible(visible) {
        const hero = $("#empty-state");
        if (!hero) return;
        if (!visible) {
            disposeRenderer("globe");
            hero.classList.add("fade-out");
            hero.style.display = "none";
        } else {
            hero.style.display = "";
            requestAnimationFrame(() => hero.classList.remove("fade-out"));
        }
    }

    function resetProgress() {
        state.moduleDone.clear();
        $("#progress-panel")?.classList.add("active");
        $("#overall-status").textContent = "Running";
        $("#overall-status").className = "status-badge status-warn";
        $("#progress-fill").style.width = "4%";
        $("#terminal-log").innerHTML = "";
        $("#batch-progress-grid").innerHTML = "";
        $$(".module-chip").forEach(chip => {
            chip.className = "module-chip waiting";
        });
    }

    function addLog(module, message, level = "info") {
        const log = $("#terminal-log");
        if (!log) return;
        const line = document.createElement("div");
        line.className = `log-line ${level === "error" ? "error" : ""}`;
        line.innerHTML = `<strong>${escapeHtml(module)}</strong><span>${escapeHtml(message)}</span>`;
        log.appendChild(line);
        log.scrollTop = log.scrollHeight;
    }

    function setModuleStatus(module, status) {
        const normalized = module === "deps" ? "dependencies" : module;
        const chip = $(`.module-chip[data-module="${normalized}"]`);
        if (!chip) return;
        chip.classList.remove("waiting", "running", "done", "error");
        chip.classList.add(status);
        if (status === "done") state.moduleDone.add(normalized);
        const pct = Math.max(4, Math.round((state.moduleDone.size / 3) * 100));
        $("#progress-fill").style.width = `${pct}%`;
    }

    function handleProgressEvent(data) {
        const module = data.module || "system";
        const event = data.event || "progress";
        const message = data.data || data.error || event;
        const level = data.level || "info";
        addLog(module, message, level);

        if (module !== "system" && module !== "cache") {
            if (event === "module_done") setModuleStatus(module, "done");
            else if (event === "module_error") setModuleStatus(module, "error");
            else setModuleStatus(module, "running");
        }
    }

    function completeProgress() {
        $("#progress-fill").style.width = "100%";
        $("#overall-status").textContent = "Complete";
        $("#overall-status").className = "status-badge status-pass";
    }

    function parseSseBlock(block) {
        const lines = block.split(/\r?\n/);
        let event = "message";
        const data = [];
        for (const line of lines) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
        }
        let parsed = data.join("\n");
        try { parsed = JSON.parse(parsed); } catch (error) {}
        return { event, data: parsed };
    }

    async function streamPost(url, payload, onEvent) {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            let message = `Request failed with ${response.status}`;
            try {
                const body = await response.json();
                message = body.error || message;
            } catch (error) {}
            throw new Error(message);
        }
        if (!response.body) throw new Error("Streaming response is unavailable in this browser.");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split(/\n\n/);
            buffer = parts.pop() || "";
            for (const part of parts) {
                if (!part.trim()) continue;
                onEvent(parseSseBlock(part));
            }
        }
        if (buffer.trim()) onEvent(parseSseBlock(buffer));
    }

    function renderSkeleton(targetId, rows = 4) {
        const target = $(`#${targetId}`);
        if (!target) return;
        target.innerHTML = `
            <div class="skeleton-card">
                <div style="width:100%;display:grid;gap:14px;">
                    ${Array.from({ length: rows }).map((_, idx) => `<div class="skeleton" style="height:${idx === 0 ? 42 : 74}px;"></div>`).join("")}
                </div>
            </div>
        `;
    }

    async function runSingleAnalysis(repo) {
        state.currentRepo = repo;
        setInputError("");
        resetProgress();
        setMarketingVisible(false);
        $("#results-shell")?.classList.add("active");
        renderSkeleton("overview-content");
        renderSkeleton("cicd-content");
        renderSkeleton("deps-content");

        $("#analyze-btn").disabled = true;
        try {
            let finalData = null;
            await streamPost("/api/analyze/full", { repo }, ({ event, data }) => {
                if (event === "progress") handleProgressEvent(data);
                if (event === "error") {
                    addLog("system", data.error || "Analysis failed", "error");
                    throw new Error(data.error || "Analysis failed");
                }
                if (event === "done") finalData = data;
            });

            if (!finalData) throw new Error("Analysis stream ended without a result.");
            state.current = normalizeAnalysisPayload(finalData);
            state.currentRepo = getRepoFromData(state.current);
            renderAll();
            completeProgress();
            switchTab("overview", true);
            showToast(finalData.cache_hit ? "Loaded cached analysis" : "Repository analysis complete", "success");
            await enrichMetadataDetails(state.current);
            await loadHistory();
        } catch (error) {
            $("#overall-status").textContent = "Failed";
            $("#overall-status").className = "status-badge status-fail";
            addLog("system", error.message, "error");
            showToast(error.message, "error");
        } finally {
            $("#analyze-btn").disabled = false;
        }
    }

    function initAnalyzeForm() {
        $("#analysis-form")?.addEventListener("submit", event => {
            event.preventDefault();
            const repo = normalizeRepoSlug($("#repo-input")?.value);
            if (!repo) {
                setInputError("Enter a valid GitHub repository, URL, or .git URL.");
                showToast("Invalid repository format", "warning");
                return;
            }
            $("#repo-input").value = repo;
            runSingleAnalysis(repo);
        });

        $("#hero-focus-btn")?.addEventListener("click", () => {
            $("#repo-input")?.focus();
        });
    }

    function parseBatchRepos() {
        const text = $("#batch-input")?.value || "";
        const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
        const repos = [];
        const invalid = [];
        for (const line of lines) {
            const repo = normalizeRepoSlug(line);
            if (repo) repos.push(repo);
            else invalid.push(line);
        }
        return { lines, repos: Array.from(new Set(repos)), invalid };
    }

    function updateBatchPreview() {
        const { lines, repos, invalid } = parseBatchRepos();
        const preview = $("#batch-preview");
        if (!preview) return;
        preview.textContent = `${repos.length} valid / ${lines.length} total${invalid.length ? `, ${invalid.length} invalid` : ""}`;
    }

    function initBatch() {
        $("#batch-input")?.addEventListener("input", updateBatchPreview);
        $("#batch-upload-btn")?.addEventListener("click", () => $("#batch-file")?.click());
        $("#batch-file")?.addEventListener("change", async event => {
            const file = event.target.files?.[0];
            if (!file) return;
            $("#batch-input").value = await file.text();
            updateBatchPreview();
            showToast("Batch file loaded", "success");
        });
        $("#batch-run-btn")?.addEventListener("click", runBatchAnalysis);
    }

    function initBatchGrid(repos) {
        const grid = $("#batch-progress-grid");
        grid.innerHTML = repos.map(repo => `
            <div class="batch-item waiting" data-repo="${escapeHtml(repo)}">
                <strong>${escapeHtml(repo)}</strong>
                <span>Queued</span>
            </div>
        `).join("");
    }

    function updateBatchItem(repo, status, text) {
        const item = $(`.batch-item[data-repo="${CSS.escape(repo)}"]`);
        if (!item) return;
        item.classList.remove("waiting", "running", "done", "failed");
        item.classList.add(status);
        item.querySelector("span").textContent = text;
    }

    async function runBatchAnalysis() {
        const { repos, invalid } = parseBatchRepos();
        if (!repos.length) {
            showToast("Add at least one valid repository for batch analysis", "warning");
            return;
        }
        if (invalid.length) showToast(`${invalid.length} invalid entries skipped`, "warning");

        resetProgress();
        setMarketingVisible(false);
        initBatchGrid(repos);
        state.batchResults = [];
        const batchId = `batch_${Date.now()}`;

        $("#batch-run-btn").disabled = true;
        try {
            await streamPost("/api/batch/analyze", { repos, batch_id: batchId }, ({ event, data }) => {
                if (event === "batch_progress") {
                    state.activeBatchRepo = data.repo;
                    updateBatchItem(data.repo, "running", `${data.current}/${data.total} running`);
                    addLog("batch", `Analyzing ${data.repo} (${data.current}/${data.total})`);
                    return;
                }
                if (event === "repo_failed") {
                    updateBatchItem(normalizeRepoSlug(data.repo) || data.repo, "failed", data.error || "Failed");
                    return;
                }
                if (event === "progress") {
                    handleProgressEvent(data);
                    return;
                }
                if (event === "done") {
                    state.batchResults.push(normalizeAnalysisPayload(data));
                    updateBatchItem(data.repo, "done", "Complete");
                    return;
                }
                if (event === "batch_done") {
                    renderBatchSummary(data.map(normalizeAnalysisPayload));
                }
            });
            completeProgress();
            switchTab("overview", true);
            showToast("Batch analysis complete", "success");
            await loadHistory();
        } catch (error) {
            addLog("batch", error.message, "error");
            showToast(error.message, "error");
        } finally {
            $("#batch-run-btn").disabled = false;
        }
    }

    function normalizeAnalysisPayload(payload) {
        const data = payload || {};
        return {
            ...data,
            repo: normalizeRepoSlug(data.repo || data.repository || data.metadata?.full_name || data.cicd?.slug) || data.repo || "",
            metadata: data.metadata || data.metadata_json || {},
            cicd: data.cicd || data.cicd_json || {},
            dependencies: data.dependencies || data.dependencies_json || {}
        };
    }

    function getDependencies(data = state.current) {
        const deps = data?.dependencies || {};
        return Array.isArray(deps.dependencies) ? deps.dependencies : [];
    }

    function getHealth(data = state.current) {
        return data?.dependencies?.health || {
            score: data?.health_score,
            risk_level: data?.risk_level
        };
    }

    function getHealthScore(data = state.current) {
        return clamp(getHealth(data).score ?? data?.health_score ?? 0);
    }

    function getRepoInfo(data = state.current) {
        return data?.metadata_details?.repository ||
            data?.dependencies?.repo_info ||
            data?.cicd?.meta ||
            data?.metadata ||
            {};
    }

    async function enrichMetadataDetails(data) {
        const repoId = data?.metadata?.repo_id;
        if (!repoId) return;
        try {
            const response = await fetch(`/api/meta/repos/${repoId}/metrics`);
            if (!response.ok) return;
            data.metadata_details = await response.json();
            if (state.current === data) renderOverview(data);
        } catch (error) {
            addLog("metadata", "Deep metadata metrics unavailable", "info");
        }
    }

    function riskClass(risk, score) {
        const value = String(risk || "").toUpperCase();
        if (value.includes("LOW") || Number(score) >= 80) return "pass";
        if (value.includes("MED") || Number(score) >= 60) return "warn";
        if (value.includes("HIGH") || value.includes("CRITICAL")) return "fail";
        return "info";
    }

    function renderAll() {
        renderOverview(state.current);
        renderCicd(state.current);
        renderDeps(state.current);
    }

    function kpi(label, value, hint = "") {
        return `
            <article class="kpi-card">
                <div class="label">${escapeHtml(label)}</div>
                <div class="value" data-count="${Number(value) || 0}">${escapeHtml(formatNumber(value))}</div>
                <div class="hint">${escapeHtml(hint)}</div>
            </article>
        `;
    }

    function renderOverview(data) {
        const target = $("#overview-content");
        if (!target) return;
        if (!data) {
            target.innerHTML = emptyCard("Overview", "Run an analysis to see repository metadata, contributors, README, commits, and file tree.");
            return;
        }

        const repoInfo = getRepoInfo(data);
        const meta = data.metadata || {};
        const stars = repoInfo.stars ?? repoInfo.stargazers_count ?? data.stars ?? meta.stars ?? 0;
        const forks = repoInfo.forks ?? repoInfo.forks_count ?? data.forks ?? 0;
        const issues = repoInfo.open_issues ?? repoInfo.open_issues_count ?? data.open_issues ?? 0;
        const commits = meta.total_commits ?? data.metadata_details?.commits?.length ?? 0;
        const contributors = meta.total_contributors ?? data.metadata_details?.contributors?.length ?? 0;
        const topics = normalizeTopics(repoInfo.topics ?? data.topics);
        const duration = data.analysis_duration_ms || 0;

        target.innerHTML = `
            <div class="kpi-grid">
                ${kpi("Stars", stars, "GitHub popularity")}
                ${kpi("Forks", forks, "Community copies")}
                ${kpi("Commits", commits, "Total or sampled activity")}
                ${kpi("Contributors", contributors, "Loaded contributors")}
            </div>

            <div class="content-grid">
                <article class="content-card">
                    <div class="card-heading">
                        <div>
                            <span class="eyebrow">Repository Summary</span>
                            <h3>${escapeHtml(repoInfo.full_name || repoInfo.name || getRepoFromData(data))}</h3>
                        </div>
                    </div>
                    <div class="summary-list">
                        ${summaryRow("Language", repoInfo.language || meta.language || data.language || "Unknown")}
                        ${summaryRow("Default branch", repoInfo.default_branch || data.default_branch || "N/A")}
                        ${summaryRow("License", formatLicense(repoInfo.license || data.license_name || "N/A"))}
                        ${summaryRow("Open issues", formatNumber(issues))}
                        ${summaryRow("Analysis duration", `${formatNumber(duration)} ms`)}
                        ${summaryRow("GitHub URL", repoInfo.url || repoInfo.html_url || "N/A")}
                    </div>
                    <div class="chip-row" style="margin-top:14px;">
                        ${topics.length ? topics.slice(0, 10).map(topic => `<span class="badge info">${escapeHtml(topic)}</span>`).join("") : `<span class="badge">No topics loaded</span>`}
                    </div>
                </article>

                <article class="content-card">
                    <div class="card-heading">
                        <div>
                            <span class="eyebrow">Metadata Module</span>
                            <h3>Extraction coverage</h3>
                        </div>
                    </div>
                    <div class="summary-list">
                        ${summaryRow("Status", meta.status || "Loaded")}
                        ${summaryRow("Repo id", meta.repo_id || "N/A")}
                        ${summaryRow("Commits analyzed", formatNumber(meta.commits_analyzed ?? data.metadata_details?.commits?.length ?? 0))}
                        ${summaryRow("Contributors loaded", formatNumber(meta.contributors_loaded ?? data.metadata_details?.contributors?.length ?? 0))}
                        ${summaryRow("Files loaded", formatNumber(data.metadata_details?.file_trees?.length ?? 0))}
                    </div>
                </article>
            </div>

            ${renderActivitySections(data)}
        `;
        countUpAll(target);
    }

    function normalizeTopics(value) {
        if (Array.isArray(value)) return value.filter(Boolean);
        if (typeof value === "string") return value.split(",").map(item => item.trim()).filter(Boolean);
        return [];
    }

    function summaryRow(label, value) {
        return `<div class="summary-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
    }

    function renderActivitySections(data) {
        const details = data.metadata_details || {};
        const contributors = details.contributors || [];
        const commits = details.commits || [];
        const files = details.file_trees || [];
        const readme = details.repository?.readme || "";
        if (!contributors.length && !commits.length && !files.length && !readme) {
            return `
                <article class="content-card">
                    <div class="card-heading"><div><span class="eyebrow">Metadata Details</span><h3>Deep repository metrics</h3></div></div>
                    <p class="muted">Contributor cards, commit timeline, README, and file tree load when the metadata module returns a repository id.</p>
                </article>
            `;
        }
        const maxCommits = contributors[0]?.total_commits || 1;
        return `
            <div class="content-grid overview-activity-grid">
                <article class="content-card contributors-card">
                    <div class="card-heading"><div><span class="eyebrow">Contributors</span><h3>Top contributors</h3></div></div>
                    <div class="bar-list">
                        ${contributors.slice(0, 8).map(item => barRow(item.username, item.total_commits, maxCommits, "var(--primary)")).join("") || `<p class="muted">No contributors returned.</p>`}
                    </div>
                    <div class="contributors-grid">
                        ${contributors.slice(0, 8).map(renderContributorCard).join("")}
                    </div>
                </article>
                <article class="content-card overview-commits-card">
                    <div class="card-heading"><div><span class="eyebrow">Commits</span><h3>Recent activity</h3></div></div>
                    <div class="activity-window">
                        ${commits.slice(0, 30).map(renderCommitItem).join("") || `<div class="notice-card"><p class="muted">No commits returned.</p></div>`}
                    </div>
                </article>
            </div>
            <article class="content-card">
                <div class="card-heading">
                    <div><span class="eyebrow">File Tree</span><h3>Repository structure</h3></div>
                    <span class="badge info">${formatNumber(files.length)} entries</span>
                </div>
                <div class="file-tree">
                    ${files.slice(0, 180).map(renderFileRow).join("") || `<div class="notice-card"><p class="muted">No file tree returned.</p></div>`}
                </div>
            </article>
            <article class="content-card">
                <div class="card-heading"><div><span class="eyebrow">README</span><h3>Repository documentation</h3></div></div>
                ${renderReadme(readme)}
            </article>
        `;
    }

    function formatLicense(value) {
        if (!value) return "N/A";
        if (typeof value === "object") return value.spdx_id || value.name || "N/A";
        return value;
    }

    function renderContributorCard(item) {
        const name = item.username || item.login || "unknown";
        const commits = item.total_commits ?? item.contributions ?? 0;
        const profile = item.profile_url || item.html_url || "";
        const avatar = item.avatar_url || "";
        const avatarHtml = avatar
            ? `<img src="${escapeHtml(avatar)}" alt="${escapeHtml(name)} avatar" loading="lazy">`
            : `<span class="avatar-fallback">${escapeHtml(name.slice(0, 2).toUpperCase())}</span>`;
        const nameHtml = profile
            ? `<a href="${escapeHtml(profile)}" target="_blank" rel="noopener"><strong>${escapeHtml(name)}</strong></a>`
            : `<strong>${escapeHtml(name)}</strong>`;
        return `
            <div class="contributor-card">
                ${avatarHtml}
                <div>
                    ${nameHtml}
                    <span>${formatNumber(commits)} commits</span>
                </div>
                <span class="badge mono">${compactNumber(commits)}</span>
            </div>
        `;
    }

    function renderCommitItem(commit) {
        const hash = String(commit.commit_hash || commit.sha || "").slice(0, 7) || "commit";
        const author = commit.author_name || commit.author || "Unknown";
        const message = commit.message || "Commit";
        const timestamp = commit.timestamp || commit.date || "";
        return `
            <div class="commit-item">
                <div class="commit-meta">
                    <strong class="mono">${escapeHtml(hash)}</strong>
                    <time>${escapeHtml(formatDate(timestamp))}</time>
                </div>
                <div class="commit-copy">
                    <strong>${escapeHtml(author)}</strong>
                    <p>${escapeHtml(message)}</p>
                </div>
            </div>
        `;
    }

    function formatDate(value) {
        if (!value) return "Unknown";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value);
        return date.toLocaleString();
    }

    function renderReadme(readme) {
        const text = String(readme || "").trim();
        if (!text || text === "No README file found.") {
            return `<div class="readme-box"><p class="muted">No README file found.</p></div>`;
        }
        try {
            if (window.marked && window.DOMPurify) {
                return `<div class="readme-box">${DOMPurify.sanitize(marked.parse(text))}</div>`;
            }
        } catch (error) {}
        return `<div class="readme-box"><pre>${escapeHtml(text)}</pre></div>`;
    }

    function renderFileRow(file) {
        const type = file.file_type || file.type || "blob";
        const path = file.file_path || file.path || "";
        const size = file.size == null ? "" : `${formatNumber(file.size)} bytes`;
        return `
            <div class="file-row">
                <span>${escapeHtml(type)}</span>
                <strong title="${escapeHtml(path)}">${escapeHtml(path)}</strong>
                <small>${escapeHtml(size)}</small>
            </div>
        `;
    }

    function barRow(label, value, max, color = "var(--primary)") {
        const pct = max ? Math.max(5, Math.round((Number(value) / Number(max)) * 100)) : 0;
        return `
            <div class="bar-row">
                <span>${escapeHtml(label)}</span>
                <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${color};"></div></div>
                <strong class="mono">${escapeHtml(formatNumber(value))}</strong>
            </div>
        `;
    }

    function collectCicdFindings(cicd) {
        const findings = [];
        for (const sec of cicd.security_results || []) {
            const secFindings = sec.findings || sec.failed_checks || [];
            for (const item of secFindings) {
                findings.push({ ...item, file: sec.file, score: sec.score });
            }
            if (sec.issues_found && !secFindings.length) {
                findings.push({ title: `${sec.issues_found} issues`, severity: "medium", file: sec.file, score: sec.score });
            }
        }
        return findings;
    }

    function collectPassedChecks(cicd) {
        const checks = [];
        for (const sec of cicd.security_results || []) {
            for (const item of sec.passed || sec.passed_checks || []) {
                checks.push({ ...item, file: sec.file });
            }
        }
        return checks;
    }

    function renderCicd(data) {
        const target = $("#cicd-content");
        if (!target) return;
        if (!data) {
            target.innerHTML = emptyCard("CI/CD", "Run an analysis to detect pipeline files and security posture.");
            return;
        }

        const cicd = data.cicd || {};
        const detected = cicd.detected || {};
        const platforms = Object.keys(detected);
        const analyses = cicd.analyses || [];
        const security = cicd.security_results || [];
        const findings = collectCicdFindings(cicd);
        const passed = collectPassedChecks(cicd);
        const avgScore = security.length ? Math.round(security.reduce((sum, item) => sum + Number(item.score || 0), 0) / security.length) : null;
        const severityCounts = findings.reduce((acc, item) => {
            const key = String(item.severity || item.level || "medium").toLowerCase();
            acc[key] = (acc[key] || 0) + 1;
            return acc;
        }, {});
        const pipelineFileCount = Object.values(detected).flat().length || analyses.length;
        const latestRun = cicd.latest_run || {};

        if (!platforms.length && !security.length && !analyses.length && !cicd.report_url) {
            target.innerHTML = emptyCard("No pipeline found", "No supported CI/CD pipeline files were detected for this repository.");
            return;
        }

        target.innerHTML = `
            <div class="kpi-grid">
                ${kpi("Security score", avgScore ?? 0, avgScore == null ? "No checks available" : "Average CI/CD score")}
                ${kpi("Platforms", platforms.length, "Detected CI/CD systems")}
                ${kpi("Pipeline files", pipelineFileCount, "Files scanned")}
                ${kpi("Findings", findings.length, "Security findings")}
            </div>

            <div class="content-grid">
                <article class="chart-card">
                    <div class="card-heading"><div><span class="eyebrow">Severity</span><h3>Finding distribution</h3></div></div>
                    <div class="bar-list">
                        ${renderSeverityBars(severityCounts)}
                    </div>
                </article>
                <article class="chart-card">
                    <div class="card-heading">
                        <div><span class="eyebrow">Standalone Report</span><h3>CI/CD analyzer report</h3></div>
                        ${cicd.report_url ? `<a class="btn btn-primary" href="${escapeHtml(cicd.report_url)}" target="_blank" rel="noopener">Open Report</a>` : ""}
                    </div>
                    <p class="muted">${cicd.report_url ? "Standalone HTML report generated by the CI/CD analyzer." : "A report is generated when analyzable pipeline files are found."}</p>
                    <div class="chip-row">
                        ${platforms.map(platform => `<span class="badge info">${escapeHtml(platform)}</span>`).join("") || `<span class="badge">No platforms</span>`}
                    </div>
                    <div class="summary-list" style="margin-top:12px;">
                        ${summaryRow("Latest run", latestRun.name || latestRun.status || "N/A")}
                        ${summaryRow("Conclusion", latestRun.conclusion || "N/A")}
                        ${summaryRow("Run number", latestRun.run_number || "N/A")}
                    </div>
                </article>
            </div>

            <article class="content-card">
                <div class="card-heading">
                    <div><span class="eyebrow">Detected Pipelines</span><h3>All pipeline files</h3></div>
                    <span class="badge info">${pipelineFileCount} files</span>
                </div>
                <div class="pipeline-list">
                    ${platforms.map(platform => renderPipelineCard(platform, detected[platform])).join("") || `<p class="muted">No platform map returned.</p>`}
                </div>
            </article>

            <article class="content-card">
                <div class="card-heading">
                    <div><span class="eyebrow">Parser Output</span><h3>Pipeline structure and quality</h3></div>
                    <span class="badge info">${analyses.length} analyzed</span>
                </div>
                <div class="module-detail-grid parser-output-list">
                    ${analyses.map(renderPipelineAnalysisCard).join("") || `<p class="muted">No pipeline parser details returned.</p>`}
                </div>
            </article>

            <div class="content-grid">
                <article class="content-card">
                    <div class="card-heading">
                        <div><span class="eyebrow">Security Findings</span><h3>Failures and remediation</h3></div>
                        <span class="risk-badge ${findings.length ? "fail" : "pass"}">${findings.length ? "REVIEW" : "PASS"}</span>
                    </div>
                    <div class="findings-list">
                        ${findings.map(renderFindingCard).join("") || `<div class="notice-card"><p class="muted">No failed CI/CD security checks.</p></div>`}
                    </div>
                </article>
                <article class="content-card">
                    <div class="card-heading">
                        <div><span class="eyebrow">Checks Passed</span><h3>Validated controls</h3></div>
                        <span class="badge pass">${passed.length} passed</span>
                    </div>
                    <div class="checks-list">
                        ${passed.slice(0, 80).map(renderPassedCheck).join("") || `<div class="notice-card"><p class="muted">No passed check details returned.</p></div>`}
                    </div>
                </article>
            </div>

            <article class="content-card">
                <div class="card-heading"><div><span class="eyebrow">Categories</span><h3>Security category coverage</h3></div></div>
                <div class="bar-list">${renderCategoryBars(security)}</div>
            </article>
        `;
        countUpAll(target);
    }

    function renderSeverityBars(counts) {
        const entries = [
            ["critical", counts.critical || 0, "var(--danger)"],
            ["high", counts.high || 0, "var(--danger)"],
            ["medium", counts.medium || 0, "var(--warning)"],
            ["low", counts.low || 0, "var(--success)"]
        ];
        const max = Math.max(1, ...entries.map(item => item[1]));
        if (!entries.some(item => item[1])) return `<p class="muted">No severity findings to chart.</p>`;
        return entries.map(([label, value, color]) => barRow(label.toUpperCase(), value, max, color)).join("");
    }

    function renderPipelineCard(platform, files) {
        const fileList = Array.isArray(files) ? files : files?.files || [];
        return `
            <article class="pipeline-card">
                <header>
                    <h3>${escapeHtml(platform)}</h3>
                    <span class="badge info">${fileList.length} files</span>
                </header>
                <div class="chip-row">
                    ${fileList.map(file => `<span class="badge mono">${escapeHtml(file)}</span>`).join("")}
                </div>
            </article>
        `;
    }

    function renderPipelineAnalysisCard(item) {
        const jobs = Array.isArray(item.jobs) ? item.jobs : [];
        const stages = Array.isArray(item.stages) ? item.stages : [];
        const triggers = Array.isArray(item.triggers) ? item.triggers : [];
        const estimatedMinutes = item.estimated_minutes ?? item.estimated_duration_minutes;
        const features = [
            ["Caching", item.caching],
            ["Matrix", item.matrix_builds],
            ["Manual approval", item.manual_approval],
            ["Notifications", item.notifications],
            ["Security scanning", item.security_scanning]
        ];
        return `
            <article class="detail-card">
                <div class="card-heading">
                    <div>
                        <span class="eyebrow">${escapeHtml(item.platform || "Pipeline")}</span>
                        <h4 class="mono">${escapeHtml(item.file || item.name || "pipeline")}</h4>
                    </div>
                    <span class="badge info">${formatNumber(item.line_count || 0)} lines</span>
                </div>
                <div class="chip-row">
                    <span class="badge mono">${jobs.length} jobs</span>
                    <span class="badge mono">${stages.length} stages</span>
                    <span class="badge mono">${triggers.length} triggers</span>
                    ${item.complexity_score != null ? `<span class="badge warn">complexity ${escapeHtml(item.complexity_score)}</span>` : ""}
                    ${estimatedMinutes != null ? `<span class="badge">${escapeHtml(estimatedMinutes)} min est.</span>` : ""}
                </div>
                <div class="chip-row">
                    ${features.map(([label, active]) => `<span class="badge ${active ? "pass" : ""}">${escapeHtml(label)}: ${active ? "yes" : "no"}</span>`).join("")}
                </div>
                ${triggers.length ? `<p class="muted"><strong>Triggers:</strong> ${escapeHtml(triggers.join(", "))}</p>` : ""}
                ${jobs.length ? renderJobsTable(jobs) : `<p class="muted">No job detail parsed.</p>`}
                ${renderMiniList("Best practices", item.best_practices)}
                ${renderMiniList("Recommendations", item.recommendations)}
                ${item.raw_content ? `<details><summary>Raw pipeline YAML</summary><pre class="raw-pipeline">${escapeHtml(item.raw_content)}</pre></details>` : ""}
            </article>
        `;
    }

    function renderJobsTable(jobs) {
        return `
            <div class="table-wrap">
                <table class="data-table">
                    <thead>
                        <tr><th>Job</th><th>Runner/Stage</th><th>Needs</th><th>Steps</th></tr>
                    </thead>
                    <tbody>
                        ${jobs.slice(0, 16).map(job => `
                            <tr>
                                <td class="mono">${escapeHtml(job.name || job.id || "job")}</td>
                                <td>${escapeHtml(job.runner || job.stage || job.image || "N/A")}</td>
                                <td>${escapeHtml(Array.isArray(job.needs) ? job.needs.join(", ") : job.needs || "None")}</td>
                                <td>${escapeHtml(Array.isArray(job.steps) ? job.steps.map(step => step.name || step.run || step.uses || "step").slice(0, 8).join(", ") : "N/A")}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }

    function renderMiniList(title, values) {
        const list = Array.isArray(values) ? values.filter(Boolean) : [];
        if (!list.length) return "";
        return `
            <div>
                <p class="muted" style="margin-bottom:6px;"><strong>${escapeHtml(title)}</strong></p>
                <div class="chip-row">
                    ${list.slice(0, 10).map(value => `<span class="badge">${escapeHtml(formatListValue(value))}</span>`).join("")}
                </div>
            </div>
        `;
    }

    function formatListValue(value) {
        if (value && typeof value === "object") {
            return [value.priority, value.title, value.detail].filter(Boolean).join(": ");
        }
        return String(value || "");
    }

    function renderFindingCard(item) {
        const severity = String(item.severity || item.level || "medium").toUpperCase();
        const cls = severity === "LOW" ? "pass" : severity === "MEDIUM" ? "warn" : "fail";
        const lines = item.matched_lines || [];
        return `
            <article class="finding-card">
                <header>
                    <div>
                        <h4>${escapeHtml(item.name || item.title || item.rule || "Security finding")}</h4>
                        <p class="muted mono">${escapeHtml(item.rule_id || item.file || "")}</p>
                    </div>
                    <span class="badge ${cls}">${escapeHtml(severity)}</span>
                </header>
                <p class="muted">${escapeHtml(item.description || item.message || "Review this pipeline finding.")}</p>
                ${item.remediation ? `<p><strong>Fix:</strong> ${escapeHtml(item.remediation)}</p>` : ""}
                ${lines.length ? `<pre class="code-block">${escapeHtml(lines.map(line => `${line.line_num || ""}: ${line.content || ""}`).join("\n"))}</pre>` : ""}
            </article>
        `;
    }

    function renderPassedCheck(item) {
        return `
            <div class="finding-card">
                <header>
                    <h4>${escapeHtml(item.name || "Passed check")}</h4>
                    <span class="badge pass">PASS</span>
                </header>
                <p class="muted">${escapeHtml(item.category || item.file || "Security control passed.")}</p>
            </div>
        `;
    }

    function renderCategoryBars(security) {
        const totals = {};
        for (const sec of security || []) {
            for (const [category, value] of Object.entries(sec.categories || {})) {
                if (!totals[category]) totals[category] = { passed: 0, failed: 0 };
                totals[category].passed += Number(value.passed || 0);
                totals[category].failed += Number(value.failed || 0);
            }
        }
        const entries = Object.entries(totals);
        if (!entries.length) return `<p class="muted">No category data returned.</p>`;
        return entries.map(([category, value]) => {
            const total = value.passed + value.failed;
            const failedPct = total ? Math.round((value.failed / total) * 100) : 0;
            return `
                <div class="bar-row">
                    <span>${escapeHtml(category)}</span>
                    <div class="bar-track">
                        <div class="bar-fill" style="width:100%;background:linear-gradient(90deg,var(--danger) 0 ${failedPct}%,var(--success) ${failedPct}% 100%);"></div>
                    </div>
                    <strong class="mono">${formatNumber(value.failed)}/${formatNumber(total)} fail</strong>
                </div>
            `;
        }).join("");
    }

    function renderDeps(data) {
        const target = $("#deps-content");
        if (!target) return;
        if (!data) {
            target.innerHTML = emptyCard("Dependencies", "Run an analysis to see ecosystem health, dependency risk, and architecture map.");
            return;
        }

        const depsData = data.dependencies || {};
        const deps = getDependencies(data);
        const health = getHealth(data);
        const score = getHealthScore(data);
        const risk = health.risk_level || data.risk_level || "UNKNOWN";
        const alerts = depsData.dependabot_alerts || [];
        const ecosystems = Object.keys(depsData.ecosystems || {});
        const outdated = countOutdated(deps);
        const stats = health.summary_stats || {};
        const breakdown = health.breakdown || {};
        const pinned = stats.pinned_count ?? deps.filter(dep => dep.pinning_type && dep.pinning_type !== "unpinned").length;
        const unpinned = stats.unpinned_count ?? deps.filter(dep => !dep.pinning_type || dep.pinning_type === "unpinned").length;
        const repo = getRepoFromData(data);

        target.innerHTML = `
            <div class="kpi-grid">
                ${kpi("Dependency score", score, risk)}
                ${kpi("Dependencies", deps.length, "Parsed packages")}
                ${kpi("Dependabot alerts", alerts.length, "Vulnerability alerts")}
                ${kpi("Outdated", outdated, "Version drift")}
            </div>

            <div class="chart-grid">
                <article class="chart-card">
                    <div class="card-heading"><div><span class="eyebrow">Risk</span><h3>Dependency risk distribution</h3></div></div>
                    <div class="bar-list">${renderDependencyRiskBars(deps, alerts, outdated)}</div>
                </article>
                <article class="chart-card">
                    <div class="card-heading"><div><span class="eyebrow">Ecosystems</span><h3>Language package systems</h3></div></div>
                    <div class="chip-row">
                        ${ecosystems.map(name => `<span class="badge info">${escapeHtml(name)}</span>`).join("") || `<span class="badge">No manifest detected</span>`}
                    </div>
                    <p class="muted">Score status: <span class="risk-badge ${riskClass(risk, score)}">${escapeHtml(risk)}</span></p>
                    <div class="summary-list" style="margin-top:12px;">
                        ${summaryRow("Pinned", formatNumber(pinned))}
                        ${summaryRow("Unpinned", formatNumber(unpinned))}
                        ${summaryRow("Production deps", formatNumber(stats.production_deps ?? deps.filter(dep => !dep.is_dev).length))}
                        ${summaryRow("Dev deps", formatNumber(stats.dev_deps ?? deps.filter(dep => dep.is_dev).length))}
                    </div>
                </article>
            </div>

            <article class="content-card">
                <div class="card-heading">
                    <div><span class="eyebrow">Health Breakdown</span><h3>Scoring details</h3></div>
                    <span class="risk-badge ${riskClass(risk, score)}">${escapeHtml(risk)} ${Math.round(score)}/100</span>
                </div>
                <div class="bar-list">${renderHealthBreakdownBars(breakdown)}</div>
            </article>

            <article class="content-card">
                <div class="card-heading">
                    <div><span class="eyebrow">Ecosystem Detection</span><h3>Manifests and lockfiles</h3></div>
                    <span class="badge info">${ecosystems.length} ecosystems</span>
                </div>
                <div class="ecosystem-grid">
                    ${ecosystems.map(name => renderEcosystemCard(name, depsData.ecosystems[name])).join("") || `<div class="notice-card"><p class="muted">No supported manifests were detected in the repository root.</p></div>`}
                </div>
                ${(depsData.errors || []).length ? `<div class="findings-list" style="margin-top:12px;">${depsData.errors.map(error => `<div class="finding-card"><span class="badge warn">WARNING</span><p>${escapeHtml(error)}</p></div>`).join("")}</div>` : ""}
            </article>

            <article class="content-card">
                <div class="card-heading">
                    <div><span class="eyebrow">Dependabot</span><h3>Vulnerability alerts</h3></div>
                    <span class="risk-badge ${alerts.length ? "fail" : "pass"}">${alerts.length ? `${alerts.length} alerts` : "No alerts"}</span>
                </div>
                <div class="dependabot-grid">
                    ${alerts.map(renderDependabotAlert).join("") || `<div class="notice-card"><p class="muted">No Dependabot alerts returned, or the token does not have access to alerts for this repository.</p></div>`}
                </div>
            </article>

            <article class="content-card">
                <div class="card-heading">
                    <div><span class="eyebrow">Dependency Inventory</span><h3>Parsed packages table</h3></div>
                    <span class="badge info">${formatNumber(deps.length)} rows</span>
                </div>
                ${renderDependencyTable(deps, alerts)}
            </article>

            <article class="content-card architecture-frame-card">
                <div class="card-heading">
                    <div>
                        <span class="eyebrow">Architecture Map</span>
                        <h3>CodeFlow workspace</h3>
                        <p class="muted">Loaded for <span class="mono">${escapeHtml(repo || "No repo selected")}</span></p>
                    </div>
                    <div class="architecture-actions">
                        <button class="btn btn-secondary" id="reload-architecture-btn" type="button">Reload Map</button>
                        <a class="btn btn-primary" id="open-architecture-link" href="${escapeHtml(buildCodeflowUrl(repo))}" target="_blank" rel="noopener">Open Full Screen</a>
                    </div>
                </div>
                <div class="architecture-frame-wrap">
                    <div class="frame-loading active" id="architecture-loading">Loading CodeFlow architecture map...</div>
                    <iframe class="architecture-frame" id="architecture-frame" title="CodeFlow Architecture Map" loading="lazy" referrerpolicy="no-referrer"></iframe>
                </div>
            </article>
        `;
        countUpAll(target);
        loadArchitectureFrame(repo);
        $("#reload-architecture-btn")?.addEventListener("click", () => loadArchitectureFrame(repo, true));
    }

    function renderHealthBreakdownBars(breakdown) {
        const labels = [
            ["pinning_quality", "Pinning quality", 40],
            ["range_tightness", "Range tightness", 20],
            ["count_risk", "Dependency count", 15],
            ["outdated_flags", "Outdated flags", 15],
            ["completeness", "Manifest completeness", 10],
            ["cve_penalty", "CVE penalty", 30],
            ["license_penalty", "License penalty", 30],
            ["maintenance_penalty", "Maintenance penalty", 30]
        ];
        const rows = labels.filter(([key]) => breakdown[key] != null);
        if (!rows.length) return `<p class="muted">No score breakdown returned.</p>`;
        return rows.map(([key, label, max]) => {
            const value = Number(breakdown[key] || 0);
            const color = key.includes("penalty") ? "var(--danger)" : "var(--primary)";
            return barRow(label, value, max, color);
        }).join("");
    }

    function renderEcosystemCard(name, info = {}) {
        const manifests = info.manifest_files || [];
        const locks = info.lock_files || [];
        return `
            <div class="notice-card">
                <div class="card-heading">
                    <div>
                        <span class="eyebrow">${escapeHtml(name)}</span>
                        <h3>${escapeHtml(name)} ecosystem</h3>
                    </div>
                    <span class="badge ${info.has_lock_file ? "pass" : "warn"}">${info.has_lock_file ? "lockfile" : "no lockfile"}</span>
                </div>
                <div class="chip-row">
                    ${manifests.map(file => `<span class="badge mono">${escapeHtml(file)}</span>`).join("") || `<span class="badge">No manifest list</span>`}
                    ${locks.map(file => `<span class="badge pass mono">${escapeHtml(file)}</span>`).join("")}
                </div>
                ${info.indicator_count != null ? `<p class="muted">${formatNumber(info.indicator_count)} ecosystem indicators found.</p>` : ""}
            </div>
        `;
    }

    function renderDependabotAlert(alert) {
        const pkg = alertPackage(alert) || "unknown package";
        const vuln = alert.security_vulnerability || {};
        const severity = String(vuln.severity || alert.severity || "unknown").toUpperCase();
        const cls = severity === "LOW" ? "pass" : severity === "MEDIUM" ? "warn" : "fail";
        const advisory = alert.security_advisory || {};
        return `
            <div class="finding-card">
                <header>
                    <div>
                        <h4 class="mono">${escapeHtml(pkg)}</h4>
                        <p class="muted">${escapeHtml(advisory.summary || vuln.vulnerable_version_range || alert.state || "Dependabot alert")}</p>
                    </div>
                    <span class="badge ${cls}">${escapeHtml(severity)}</span>
                </header>
                <div class="chip-row">
                    ${vuln.package?.ecosystem ? `<span class="badge">${escapeHtml(vuln.package.ecosystem)}</span>` : ""}
                    ${vuln.vulnerable_version_range ? `<span class="badge mono">${escapeHtml(vuln.vulnerable_version_range)}</span>` : ""}
                    ${vuln.first_patched_version?.identifier ? `<span class="badge pass mono">patched ${escapeHtml(vuln.first_patched_version.identifier)}</span>` : ""}
                </div>
            </div>
        `;
    }

    function renderDependencyTable(deps, alerts) {
        if (!deps.length) return emptyCard("No dependencies", "No supported dependency manifests were found.");
        return `
            <div class="table-wrap">
                <table class="data-table dependency-table">
                    <thead>
                        <tr>
                            <th style="width:18%;">Package</th>
                            <th style="width:12%;">Version</th>
                            <th style="width:11%;">Pinning</th>
                            <th style="width:18%;">Source</th>
                            <th style="width:8%;">Scope</th>
                            <th style="width:9%;">Depth</th>
                            <th style="width:10%;">License</th>
                            <th style="width:8%;">Latest</th>
                            <th style="width:10%;">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${deps.map(dep => renderDependencyTableRow(dep, alerts)).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }

    function depName(dep) {
        return dep.name || dep.package || dep.dependency || "unknown";
    }

    function depVersion(dep) {
        return dep.version_constraint || dep.version || dep.current_version || dep.constraint || "";
    }

    function depStatus(dep, alerts) {
        const name = depName(dep);
        const vulnerable = alerts.some(alert => alertPackage(alert) === name);
        const latest = dep.latest_version;
        const current = depVersion(dep);
        const outdated = dep.is_outdated === true || (latest && current && String(latest) !== String(current));
        if (vulnerable) return ["VULNERABLE", "fail"];
        if (outdated) return ["OUTDATED", "warn"];
        if (!current || current === "*" || dep.pinning_type === "unpinned") return ["UNPINNED", "warn"];
        return ["PASS", "pass"];
    }

    function renderDependencyTableRow(dep, alerts) {
        const [status, cls] = depStatus(dep, alerts);
        const version = depVersion(dep) || "N/A";
        return `
            <tr>
                <td class="mono">${escapeHtml(depName(dep))}</td>
                <td class="mono">${escapeHtml(version)}</td>
                <td><span class="badge ${dep.pinning_type === "exact" ? "pass" : dep.pinning_type === "unpinned" ? "warn" : "info"}">${escapeHtml(dep.pinning_type || "unknown")}</span></td>
                <td class="mono">${escapeHtml(dep.source_file || dep.file || "N/A")}</td>
                <td>${escapeHtml(dep.is_dev ? "dev" : "prod")}</td>
                <td>${escapeHtml(dep.is_transitive ? "transitive" : "direct")}</td>
                <td>${escapeHtml(dep.license || "unknown")}</td>
                <td class="mono">${escapeHtml(dep.latest_version || "N/A")}</td>
                <td><span class="badge ${cls}">${escapeHtml(status)}</span></td>
            </tr>
        `;
    }

    function countOutdated(deps) {
        return deps.filter(dep => {
            const latest = dep.latest_version;
            const current = dep.version_constraint || dep.version || dep.current_version || dep.constraint;
            return dep.is_outdated === true || (latest && current && String(latest) !== String(current));
        }).length;
    }

    function alertPackage(alert) {
        return alert?.dependency?.package?.name || alert?.security_vulnerability?.package?.name || alert?.package || "";
    }

    function renderDependencyRiskBars(deps, alerts, outdated) {
        const direct = deps.filter(dep => !dep.is_transitive).length;
        const transitive = Math.max(0, deps.length - direct);
        const rows = [
            ["Vulnerable", alerts.length, "var(--danger)"],
            ["Outdated", outdated, "var(--warning)"],
            ["Direct", direct, "var(--primary)"],
            ["Transitive", transitive, "var(--blue-muted)"]
        ];
        const max = Math.max(1, ...rows.map(row => row[1]));
        return rows.map(([label, value, color]) => barRow(label, value, max, color)).join("");
    }

    function renderDependencyRow(dep, alerts) {
        const name = dep.name || dep.package || "unknown";
        const vulnerable = alerts.some(alert => alertPackage(alert) === name);
        const latest = dep.latest_version;
        const current = dep.version || dep.current_version || dep.constraint || "N/A";
        const outdated = dep.is_outdated === true || (latest && current && String(latest) !== String(current));
        const badge = vulnerable ? `<span class="badge fail">VULNERABLE</span>` : outdated ? `<span class="badge warn">OUTDATED</span>` : `<span class="badge pass">PASS</span>`;
        return `
            <article class="dependency-row">
                <header>
                    <h3 class="mono">${escapeHtml(name)}</h3>
                    ${badge}
                </header>
                <div class="chip-row">
                    <span class="badge">${escapeHtml(dep.ecosystem || dep.source || "package")}</span>
                    <span class="badge mono">current ${escapeHtml(current)}</span>
                    ${latest ? `<span class="badge mono">latest ${escapeHtml(latest)}</span>` : ""}
                    ${dep.is_transitive ? `<span class="badge">transitive</span>` : `<span class="badge info">direct</span>`}
                </div>
            </article>
        `;
    }

    function buildCodeflowUrl(repo) {
        const url = new URL("/static/codeflow/index.html", window.location.origin);
        if (repo) url.searchParams.set("repo", repo);
        url.searchParams.set("auth", "server");
        return `${url.pathname}${url.search}`;
    }

    function loadArchitectureFrame(repo, force = false) {
        const frame = $("#architecture-frame");
        const loader = $("#architecture-loading");
        const link = $("#open-architecture-link");
        if (!frame) return;
        const url = buildCodeflowUrl(repo);
        if (link) link.href = url;
        if (force || frame.dataset.repo !== repo) {
            if (loader) loader.classList.add("active");
            frame.dataset.repo = repo || "";
            frame.src = url;
            frame.onload = () => loader?.classList.remove("active");
        }
    }

    function emptyCard(title, message) {
        return `<div class="empty-card"><div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p></div></div>`;
    }

    function pipelineStatusClass(status) {
        const value = String(status || "").toLowerCase();
        if (["completed", "passed", "success"].includes(value)) return "pass";
        if (["running", "pending", "skipped"].includes(value)) return "warn";
        if (["failed", "blocked", "error", "needs_human"].includes(value)) return "fail";
        return "info";
    }

    function humanizeStatus(value) {
        return String(value || "unknown")
            .replace(/_/g, " ")
            .replace(/\b\w/g, char => char.toUpperCase());
    }

    function formatDateTime(value) {
        if (!value) return "N/A";
        try {
            return new Date(value).toLocaleString();
        } catch (error) {
            return String(value);
        }
    }

    function formatCompactDateTime(value) {
        if (!value) return "N/A";
        try {
            return new Date(value).toLocaleString(undefined, {
                month: "short",
                day: "numeric",
                hour: "numeric",
                minute: "2-digit"
            });
        } catch (error) {
            return String(value);
        }
    }

    function shortSha(value) {
        const sha = String(value || "");
        return sha ? sha.slice(0, 8) : "N/A";
    }

    function getPipelineStage(run, stageName) {
        return (run.stages || []).find(stage => stage.stage_name === stageName) || null;
    }

    function stageStatusBadge(run, stageName, label) {
        const stage = getPipelineStage(run, stageName);
        const status = stage?.status || "pending";
        return `<span class="badge ${pipelineStatusClass(status)}"><span class="pill-status">${escapeHtml(label)}</span>${escapeHtml(humanizeStatus(status))}</span>`;
    }

    async function loadPipelineRuns({ silent = false } = {}) {
        const target = $("#pipeline-content");
        if (!target) return;
        target.innerHTML = emptyCard("Pipeline Monitor", "Loading autonomous pipeline runs.");
        try {
            const response = await fetch("/api/pipeline/runs?limit=100");
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Could not load pipeline runs");
            state.pipelineRuns = Array.isArray(data) ? data : [];
            renderPipelineMonitor();
        } catch (error) {
            target.innerHTML = emptyCard("Pipeline Monitor unavailable", error.message);
            if (!silent) showToast(error.message, "error");
        }
    }

    function renderPipelineMonitor() {
        const target = $("#pipeline-content");
        if (!target) return;
        if (!state.pipelineRuns.length) {
            target.innerHTML = emptyCard("No pipeline runs yet", "GitHub Actions quality reports will appear here after /api/quality/report receives data.");
            return;
        }
        target.innerHTML = `
            <div class="pipeline-monitor-toolbar">
                <input id="pipeline-filter-repo" type="search" placeholder="Filter repo">
                <select id="pipeline-filter-status">
                    <option value="">All statuses</option>
                    <option value="running">Running</option>
                    <option value="completed">Completed</option>
                    <option value="failed">Failed</option>
                    <option value="blocked">Blocked</option>
                    <option value="needs_human">Needs human</option>
                    <option value="error">Error</option>
                </select>
                <select id="pipeline-filter-stage">
                    <option value="">All stages</option>
                    <option value="quality_gate">Quality gate</option>
                    <option value="compiler_check">Compiler check</option>
                    <option value="ai_remediation">AI remediation</option>
                    <option value="final_verification">Final verification</option>
                </select>
                <select id="pipeline-filter-severity">
                    <option value="">All severities</option>
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                </select>
                <input id="pipeline-filter-date" type="date">
                <button class="btn btn-secondary" id="pipeline-refresh-btn" type="button">Refresh</button>
            </div>
            <div class="table-wrap">
                <table class="data-table pipeline-monitor-table">
                    <thead>
                        <tr>
                            <th>Repo</th>
                            <th>Branch</th>
                            <th>Commit</th>
                            <th>PR</th>
                            <th>Workflow</th>
                            <th>Stages</th>
                            <th>Findings</th>
                            <th>Reports</th>
                            <th>Last run</th>
                        </tr>
                    </thead>
                    <tbody id="pipeline-table-body"></tbody>
                </table>
            </div>
        `;
        $("#pipeline-filter-repo").addEventListener("input", applyPipelineFilters);
        $("#pipeline-filter-status").addEventListener("change", applyPipelineFilters);
        $("#pipeline-filter-stage").addEventListener("change", applyPipelineFilters);
        $("#pipeline-filter-severity").addEventListener("change", applyPipelineFilters);
        $("#pipeline-filter-date").addEventListener("change", applyPipelineFilters);
        $("#pipeline-refresh-btn").addEventListener("click", () => loadPipelineRuns());
        applyPipelineFilters();
    }

    function applyPipelineFilters() {
        const body = $("#pipeline-table-body");
        if (!body) return;
        const repoQuery = ($("#pipeline-filter-repo")?.value || "").toLowerCase();
        const status = $("#pipeline-filter-status")?.value || "";
        const stageName = $("#pipeline-filter-stage")?.value || "";
        const severity = $("#pipeline-filter-severity")?.value || "";
        const date = $("#pipeline-filter-date")?.value || "";

        const filtered = state.pipelineRuns.filter(run => {
            const summary = run.quality_summary || {};
            if (repoQuery && !String(run.repo || "").toLowerCase().includes(repoQuery)) return false;
            if (status && run.overall_status !== status) return false;
            if (stageName && !getPipelineStage(run, stageName)) return false;
            if (severity && Number(summary[severity] || 0) <= 0) return false;
            if (date && !String(run.created_at || "").startsWith(date)) return false;
            return true;
        });

        body.innerHTML = filtered.length
            ? filtered.map(renderPipelineRow).join("")
            : `<tr><td colspan="9">${emptyCard("No matching pipeline runs", "Adjust filters or wait for GitHub Actions reports.")}</td></tr>`;
    }

    function renderPipelineRow(run) {
        const summary = run.quality_summary || {};
        const artifacts = run.quality_artifacts || {};
        const workflowUrl = run.raw_json?.workflow_url || run.stages?.find(stage => stage.artifacts?.workflow_url)?.artifacts?.workflow_url;
        const runUrl = run.workflow_run_id && run.repo ? `https://github.com/${run.repo}/actions/runs/${run.workflow_run_id}` : workflowUrl;
        const reports = [
            artifacts.json_report ? `<span class="badge info">${escapeHtml(artifacts.json_report)}</span>` : "",
            artifacts.html_report ? `<span class="badge info">${escapeHtml(artifacts.html_report)}</span>` : "",
            artifacts.github_artifact ? `<span class="badge">${escapeHtml(artifacts.github_artifact)}</span>` : ""
        ].filter(Boolean).join("");

        return `
            <tr>
                <td class="mono">${escapeHtml(run.repo || "N/A")}</td>
                <td>${escapeHtml(run.branch || "N/A")}</td>
                <td class="mono">${escapeHtml(shortSha(run.commit_sha))}</td>
                <td>${run.pr_number ? `#${escapeHtml(run.pr_number)}` : "N/A"}</td>
                <td>
                    <div class="chip-row">
                        <span class="badge ${pipelineStatusClass(run.overall_status)}">${escapeHtml(run.overall_status || "unknown")}</span>
                        ${runUrl ? `<a class="badge info" href="${escapeHtml(runUrl)}" target="_blank" rel="noreferrer">Run ${escapeHtml(run.workflow_run_id || "")}</a>` : `<span class="badge">Run ${escapeHtml(run.workflow_run_id || "N/A")}</span>`}
                    </div>
                </td>
                <td>
                    <div class="chip-row">
                        ${stageStatusBadge(run, "quality_gate", "Quality")}
                        ${stageStatusBadge(run, "compiler_check", "Compiler")}
                        ${stageStatusBadge(run, "ai_remediation", "AI")}
                        ${stageStatusBadge(run, "final_verification", "Final")}
                    </div>
                </td>
                <td>
                    <div class="chip-row">
                        <span class="badge fail">C ${formatNumber(summary.critical || 0)}</span>
                        <span class="badge fail">H ${formatNumber(summary.high || 0)}</span>
                        <span class="badge warn">M ${formatNumber(summary.medium || 0)}</span>
                        <span class="badge info">L ${formatNumber(summary.low || 0)}</span>
                    </div>
                </td>
                <td><div class="chip-row">${reports || `<span class="badge">No artifacts</span>`}</div></td>
                <td>${escapeHtml(formatDateTime(run.completed_at || run.created_at))}</td>
            </tr>
        `;
    }

    async function loadAuthStatus() {
        try {
            const response = await fetch("/api/auth/status");
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Could not load auth status");
            state.auth = data;
            renderAuthControls();
            renderLandingAuth();
        } catch (error) {
            state.auth = null;
            renderAuthControls(error.message);
            renderLandingAuth(error.message);
        }
    }

    function renderLandingAuth(errorMessage = "") {
        const target = $("#landing-auth-card");
        if (!target) return;
        const auth = state.auth;
        document.body.classList.toggle("is-authenticated", Boolean(auth?.authenticated));
        if (!auth) {
            target.innerHTML = `
                <span class="status-badge status-warn">Auth unavailable</span>
                <p>${escapeHtml(errorMessage || "Could not read authentication status.")}</p>
            `;
            return;
        }

        if (auth.authenticated) {
            target.innerHTML = `
                <div>
                    <span class="status-badge status-pass">Signed in</span>
                    <h3>${escapeHtml(auth.user?.github_login || "GitHub user")}</h3>
                    <p>Tenant access is ready. Continue to the dashboard to configure repositories and monitor pipelines.</p>
                </div>
                <button class="btn btn-primary" type="button" data-landing-dashboard>Open Dashboard</button>
            `;
            target.querySelector("[data-landing-dashboard]")?.addEventListener("click", () => enterDashboard({ focusInput: true }));
            return;
        }

        if (auth.github_login_configured) {
            target.innerHTML = `
                <div>
                    <span class="status-badge status-info">GitHub sign up required</span>
                    <h3>Start with your GitHub account</h3>
                    <p>Sign up to create your workspace, select a tenant, and connect repositories through the GitHub App.</p>
                </div>
                <a class="btn btn-primary" href="/api/auth/login">Sign up with GitHub</a>
            `;
            return;
        }

        target.innerHTML = `
            <div>
                <span class="status-badge status-warn">GitHub sign up not configured</span>
                <h3>Local server needs GitHub App OAuth credentials</h3>
                <p>Add <code>GITHUB_APP_CLIENT_ID</code> and <code>GITHUB_APP_CLIENT_SECRET</code> in <code>.env</code>, set <code>PUBLIC_BASE_URL=http://127.0.0.1:8000</code>, then restart the server.</p>
            </div>
            ${auth.require_login ? "" : `<button class="btn btn-secondary" type="button" data-local-dashboard>Continue local dev</button>`}
        `;
        target.querySelector("[data-local-dashboard]")?.addEventListener("click", () => enterDashboard({ focusInput: true }));
    }

    function renderAuthControls(errorMessage = "") {
        const target = $("#auth-controls");
        if (!target) return;
        const auth = state.auth;
        if (!auth) {
            target.innerHTML = `<span class="status-badge status-warn">${escapeHtml(errorMessage || "Auth unavailable")}</span>`;
            return;
        }

        const selected = auth.selected_tenant_id ? String(auth.selected_tenant_id) : "";
        const tenantOptions = (auth.tenants || []).map(tenant => `
            <option value="${escapeHtml(tenant.id)}" ${String(tenant.id) === selected ? "selected" : ""}>
                ${escapeHtml(tenant.name || tenant.slug)}
            </option>
        `).join("");

        if (!auth.authenticated) {
            target.innerHTML = `
                <a class="btn btn-secondary" href="/api/auth/login">Sign in with GitHub</a>
            `;
            return;
        }

        target.innerHTML = `
            <select id="tenant-selector" class="tenant-selector" aria-label="Select tenant">
                ${tenantOptions || `<option value="">No tenant</option>`}
            </select>
            <span class="user-pill">${auth.user?.avatar_url ? `<img src="${escapeHtml(auth.user.avatar_url)}" alt="">` : ""}${escapeHtml(auth.user?.github_login || "GitHub user")}</span>
            <button class="text-btn" id="logout-btn" type="button">Logout</button>
        `;

        $("#tenant-selector")?.addEventListener("change", async event => {
            const tenantId = event.target.value;
            try {
                const response = await fetch("/api/auth/select-tenant", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ tenant_id: Number(tenantId) })
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || "Tenant selection failed");
                showToast("Tenant selected", "success", 1800);
                await loadAuthStatus();
                if (state.activeTab === "pipeline") loadPipelineRuns({ silent: true });
                if (state.activeTab === "setup") loadSetupRepositories({ silent: true });
                await loadHistory();
            } catch (error) {
                showToast(error.message, "error");
            }
        });

        $("#logout-btn")?.addEventListener("click", async () => {
            await fetch("/api/auth/logout", { method: "POST" });
            showToast("Logged out", "success", 1800);
            await loadAuthStatus();
        });
    }

    async function loadSetupRepositories({ silent = false } = {}) {
        const target = $("#setup-content");
        if (!target) return;
        target.innerHTML = emptyCard("Repo Setup", "Loading monitored repositories.");
        try {
            const response = await fetch("/api/setup/repositories");
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Could not load repository setup status");
            state.setupRepos = Array.isArray(data) ? data : [];
            renderRepoSetup();
        } catch (error) {
            target.innerHTML = emptyCard("Repo Setup unavailable", error.message);
            if (!silent) showToast(error.message, "error");
        }
    }

    function renderRepoSetup() {
        const target = $("#setup-content");
        if (!target) return;
        const auth = state.auth || {};
        target.innerHTML = `
            <div class="setup-header">
                <div>
                    <span class="eyebrow">Repository Onboarding</span>
                    <h3>Configure enforcement for monitored repos</h3>
                    <p class="muted">Install the GitHub App, select repositories, and this app syncs and provisions enforcement automatically when production configuration is ready.</p>
                </div>
                <div class="chip-row">
                    ${auth.github_app_install_url ? `<a class="btn btn-primary" href="${escapeHtml(auth.github_app_install_url)}" target="_blank" rel="noreferrer">Install GitHub App</a>` : `<span class="status-badge status-warn">GitHub App URL missing</span>`}
                    <button class="btn btn-secondary" id="setup-sync-btn" type="button">Sync Installed Repos</button>
                    <button class="btn btn-secondary" id="setup-refresh-btn" type="button">Refresh</button>
                </div>
            </div>
            <div class="setup-note">
                <strong>Flow:</strong> GitHub App install is where repo selection happens. This app then syncs selected repos and configures each one automatically.
            </div>
            <form class="repo-register-form" id="repo-register-form">
                <input id="setup-repo-input" type="text" placeholder="owner/repo" aria-label="Repository to register">
                <button class="btn btn-secondary" type="submit">Register Repo</button>
            </form>
            <div class="table-wrap">
                <table class="data-table setup-table">
                    <thead>
                        <tr>
                            <th>Repo</th>
                            <th>Status</th>
                            <th>API Key</th>
                            <th>Workflow</th>
                            <th>Secrets</th>
                            <th>Ruleset</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${state.setupRepos.length ? state.setupRepos.map(renderSetupRepoRow).join("") : `<tr><td colspan="7">${emptyCard("No repositories registered", "Use GitHub App installation or register a repo manually for local testing.")}</td></tr>`}
                    </tbody>
                </table>
            </div>
        `;
        $("#setup-refresh-btn")?.addEventListener("click", () => loadSetupRepositories());
        $("#setup-sync-btn")?.addEventListener("click", syncInstalledRepos);
        $("#repo-register-form")?.addEventListener("submit", registerSetupRepo);
        $$(".repo-provision-btn").forEach(button => {
            button.addEventListener("click", () => provisionSetupRepo(button.dataset.repoId));
        });
    }

    function setupStatusBadge(status) {
        const value = String(status || "pending");
        const cls = value === "active" ? "pass" : value === "failed" || value === "needs_attention" ? "fail" : "warn";
        return `<span class="badge ${cls}">${escapeHtml(humanizeStatus(value))}</span>`;
    }

    function setupDate(value) {
        return value ? `<span class="badge timestamp">${escapeHtml(formatCompactDateTime(value))}</span>` : `<span class="badge pending">Pending</span>`;
    }

    function renderSetupRepoRow(repo) {
        return `
            <tr>
                <td class="mono">${escapeHtml(repo.full_name)}</td>
                <td>${setupStatusBadge(repo.setup_status)}</td>
                <td>${repo.api_key_prefix ? `<span class="badge info">${escapeHtml(repo.api_key_prefix)}</span>` : `<span class="badge warn">Not created</span>`}</td>
                <td>${setupDate(repo.workflow_installed_at)}</td>
                <td>${setupDate(repo.secrets_configured_at)}</td>
                <td>${setupDate(repo.ruleset_configured_at)}</td>
                <td><button class="btn btn-secondary repo-provision-btn" type="button" data-repo-id="${escapeHtml(repo.id)}">Configure</button></td>
            </tr>
        `;
    }

    async function registerSetupRepo(event) {
        event.preventDefault();
        const repo = normalizeRepoSlug($("#setup-repo-input")?.value);
        if (!repo) {
            showToast("Enter a valid owner/repo", "warning");
            return;
        }
        try {
            const response = await fetch("/api/setup/repositories/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ repo })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Repository registration failed");
            showToast(`${repo} registered`, "success");
            await loadSetupRepositories({ silent: true });
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    async function provisionSetupRepo(repoId) {
        if (!repoId) return;
        try {
            const response = await fetch(`/api/setup/repositories/${repoId}/provision`, { method: "POST" });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Repository provisioning failed");
            if (data.result?.dry_run) {
                showToast("Dry-run complete. Set PROVISIONING_DRY_RUN=false, restart, then Configure again to apply changes.", "warning", 7200);
            } else if (data.result?.workflow_delivery?.mode === "pull_request") {
                const prNumber = data.result.workflow_delivery.pull_request_number;
                showToast(
                    prNumber
                        ? `Setup PR #${prNumber} created. Merge it in GitHub to install the workflow.`
                        : "Setup pull request created. Merge it to install the workflow.",
                    "success",
                    9000
                );
            } else {
                showToast("Repository configured", "success");
            }
            if (data.result?.raw_api_key) {
                console.warn("Repository API key was generated and sent to GitHub Actions secret setup.");
            }
            await loadSetupRepositories({ silent: true });
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    async function syncInstalledRepos() {
        try {
            const response = await fetch("/api/setup/sync-installed-repositories", { method: "POST" });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Could not sync installed repositories");
            const count = (data.installations || []).reduce((sum, item) => sum + Number(item.repository_count || 0), 0);
            showToast(`Synced ${count} installed repositories`, "success");
            await loadSetupRepositories({ silent: true });
        } catch (error) {
            showToast(error.message, "error", 7000);
        }
    }

    function renderBatchSummary(results) {
        const target = $("#overview-content");
        const normalized = (results || state.batchResults || []).filter(item => item && item.repo && item.status !== "failed");
        const failed = (results || []).filter(item => item?.status === "failed");
        state.batchResults = normalized;
        if (!target) return;
        const success = normalized.length;
        const avg = success ? Math.round(normalized.reduce((sum, item) => sum + getHealthScore(item), 0) / success) : 0;
        target.innerHTML = `
            <div class="kpi-grid">
                ${kpi("Successful", success, "Completed repositories")}
                ${kpi("Failed", failed.length, "Skipped or failed")}
                ${kpi("Average score", avg, "Dependency health")}
                ${kpi("Batch size", success + failed.length, "Requested repositories")}
            </div>
            <div class="history-grid">
                ${failed.map(item => `<article class="failed-card"><h3>${escapeHtml(item.repo)}</h3><p class="muted">${escapeHtml(item.error || "Failed")}</p></article>`).join("")}
                ${normalized.map(item => `
                    <article class="history-card" onclick="window.repoIntelOpenResult('${escapeHtml(item.repo)}')">
                        <header>
                            <h3 class="mono">${escapeHtml(item.repo)}</h3>
                            <span class="risk-badge ${riskClass(getHealth(item).risk_level, getHealthScore(item))}">${Math.round(getHealthScore(item))}/100</span>
                        </header>
                        <p class="muted">Click to inspect this repository result.</p>
                    </article>
                `).join("")}
            </div>
        `;
        countUpAll(target);
    }

    window.repoIntelOpenResult = repo => {
        const found = state.batchResults.find(item => item.repo === repo);
        if (!found) return;
        state.current = found;
        state.currentRepo = repo;
        renderAll();
        switchTab("overview", true);
    };

    async function loadHistory() {
        try {
            const response = await fetch("/api/history");
            if (!response.ok) throw new Error("History request failed");
            state.history = (await response.json()).map(normalizeAnalysisPayload);
            $("#history-count").textContent = state.history.length;
            renderRecent();
            renderHistory();
        } catch (error) {
            $("#recent-list").innerHTML = `<div class="recent-empty">History unavailable.</div>`;
        }
    }

    function renderRecent() {
        const target = $("#recent-list");
        if (!target) return;
        const recent = state.history.slice(0, 15);
        target.innerHTML = recent.length ? recent.map(item => `
            <button class="recent-card" type="button" data-history-id="${item.id}" title="${escapeHtml(item.repo)}">
                <strong>${escapeHtml(item.repo)}</strong>
                <span>${escapeHtml(item.analyzed_at ? new Date(item.analyzed_at).toLocaleString() : "Unknown time")}</span>
            </button>
        `).join("") : `<div class="recent-empty">No analyses yet.</div>`;

        $$(".recent-card", target).forEach(card => {
            card.addEventListener("click", () => openHistoryRecord(Number(card.dataset.historyId)));
        });
    }

    function renderHistory() {
        const target = $("#history-content");
        if (!target) return;
        if (!state.history.length) {
            target.innerHTML = emptyCard("No history yet", "Completed single and batch analyses will appear here.");
            return;
        }
        target.innerHTML = `
            <div class="history-toolbar">
                <input id="history-search" type="search" placeholder="Search repositories or batch ids">
                <select id="history-risk">
                    <option value="">All risks</option>
                    <option value="LOW">Low</option>
                    <option value="MEDIUM">Medium</option>
                    <option value="HIGH">High</option>
                    <option value="UNKNOWN">Unknown</option>
                </select>
                <select id="history-type">
                    <option value="">All runs</option>
                    <option value="single">Single</option>
                    <option value="batch">Batch</option>
                </select>
                <button class="btn btn-danger" id="clear-history-btn" type="button">Clear</button>
            </div>
            <div class="history-grid" id="history-grid"></div>
        `;
        $("#history-search").addEventListener("input", applyHistoryFilters);
        $("#history-risk").addEventListener("change", applyHistoryFilters);
        $("#history-type").addEventListener("change", applyHistoryFilters);
        $("#clear-history-btn").addEventListener("click", clearHistory);
        applyHistoryFilters();
    }

    function applyHistoryFilters() {
        const grid = $("#history-grid");
        if (!grid) return;
        const query = ($("#history-search")?.value || "").toLowerCase();
        const risk = $("#history-risk")?.value || "";
        const type = $("#history-type")?.value || "";

        const filtered = state.history.filter(item => {
            const isBatch = Boolean(item.batch_id);
            if (type === "single" && isBatch) return false;
            if (type === "batch" && !isBatch) return false;
            if (risk && String(item.risk_level || "UNKNOWN").toUpperCase() !== risk) return false;
            if (!query) return true;
            return [item.repo, item.language, item.risk_level, item.batch_id].some(value => String(value || "").toLowerCase().includes(query));
        });

        grid.innerHTML = filtered.length ? filtered.map(renderHistoryCard).join("") : emptyCard("No matching history", "Adjust search or filters.");
        $$(".history-card", grid).forEach(card => {
            card.addEventListener("click", () => openHistoryRecord(Number(card.dataset.historyId)));
        });
        $$(".copy-repo", grid).forEach(btn => {
            btn.addEventListener("click", event => {
                event.stopPropagation();
                copyText(btn.dataset.repo, "Repository copied");
            });
        });
        $$(".delete-history", grid).forEach(btn => {
            btn.addEventListener("click", event => {
                event.stopPropagation();
                deleteHistoryRecord(Number(btn.dataset.id));
            });
        });
    }

    function renderHistoryCard(item) {
        const score = item.health_score ?? getHealthScore(item);
        const risk = item.risk_level || getHealth(item).risk_level || "UNKNOWN";
        return `
            <article class="history-card" data-history-id="${item.id}">
                <header>
                    <div>
                        <h3 class="mono">${escapeHtml(item.repo)}</h3>
                        <p class="muted">${escapeHtml(item.analyzed_at ? new Date(item.analyzed_at).toLocaleString() : "Unknown time")}</p>
                    </div>
                    <span class="risk-badge ${riskClass(risk, score)}">${escapeHtml(risk)} ${score != null ? `${Math.round(score)}/100` : ""}</span>
                </header>
                <div class="chip-row">
                    <span class="badge">${escapeHtml(item.language || "Unknown")}</span>
                    ${item.batch_id ? `<span class="badge info">${escapeHtml(item.batch_id)}</span>` : `<span class="badge">single</span>`}
                    <span class="badge mono">${formatNumber(item.total_dependencies || 0)} deps</span>
                </div>
                <div class="history-actions">
                    <button class="btn btn-secondary copy-repo" type="button" data-repo="${escapeHtml(item.repo)}">Copy Repo</button>
                    <a class="btn btn-secondary" href="/api/history/${item.id}/export?format=json" onclick="event.stopPropagation()">JSON</a>
                    <a class="btn btn-secondary" href="/api/history/${item.id}/export?format=markdown" onclick="event.stopPropagation()">Markdown</a>
                    <button class="btn btn-danger delete-history" type="button" data-id="${item.id}">Delete</button>
                </div>
            </article>
        `;
    }

    async function openHistoryRecord(id) {
        const local = state.history.find(item => Number(item.id) === Number(id));
        if (!local) return;
        state.current = normalizeAnalysisPayload(local);
        state.currentRepo = getRepoFromData(state.current);
        $("#repo-input").value = state.currentRepo;
        setMarketingVisible(false);
        $("#results-shell")?.classList.add("active");
        renderAll();
        switchTab("overview", true);
        showToast("History result loaded", "success", 1800);
        await enrichMetadataDetails(state.current);
    }

    async function deleteHistoryRecord(id) {
        if (!confirm("Delete this history record?")) return;
        try {
            const response = await fetch(`/api/history/${id}`, { method: "DELETE" });
            if (!response.ok) throw new Error("Delete failed");
            showToast("History record deleted", "success");
            await loadHistory();
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    async function clearHistory() {
        const count = state.history.length;
        if (!count) return;
        if (!confirm(`Clear ${count} history records?`)) return;
        if (!confirm("Final confirmation: this cannot be undone.")) return;
        try {
            const response = await fetch("/api/history", { method: "DELETE" });
            if (!response.ok) throw new Error("Clear failed");
            state.history = [];
            renderRecent();
            renderHistory();
            showToast("History cleared", "success");
        } catch (error) {
            showToast(error.message, "error");
        }
    }

    async function refreshRateLimit() {
        const text = $("#rate-limit-text");
        const pill = $("#rate-limit-pill");
        try {
            const response = await fetch("/api/rate-limit");
            const data = await response.json();
            if (!response.ok) {
                const label = data.token_configured ? "API token error" : "API no token";
                if (text) text.textContent = label;
                if (pill) pill.title = data.error || "GitHub API rate limit unavailable";
                return;
            }
            text.textContent = `API ${formatNumber(data.remaining)}/${formatNumber(data.limit)}`;
            if (pill) {
                pill.title = data.token_configured
                    ? `GitHub token active. Resets at ${data.reset_utc || "unknown time"}`
                    : "No GitHub token configured. Public rate limit is lower.";
            }
        } catch (error) {
            if (text) text.textContent = "API offline";
            if (pill) pill.title = error.message || "Could not reach the backend rate-limit endpoint";
        }
    }

    function countUpAll(root = document) {
        $$("[data-count]", root).forEach(el => {
            const target = Number(el.dataset.count || 0);
            const start = performance.now();
            const duration = 850;
            function frame(now) {
                const t = clamp((now - start) / duration, 0, 1);
                const eased = 1 - Math.pow(1 - t, 3);
                el.textContent = formatNumber(Math.round(target * eased));
                if (t < 1) requestAnimationFrame(frame);
            }
            requestAnimationFrame(frame);
        });
    }

    function threeAvailable() {
        return typeof window.THREE !== "undefined";
    }

    function fitCanvas(canvas, host) {
        const rect = host.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.max(1, Math.floor(rect.width * dpr));
        canvas.height = Math.max(1, Math.floor(rect.height * dpr));
        canvas.style.width = `${rect.width}px`;
        canvas.style.height = `${rect.height}px`;
        const ctx = canvas.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        return { ctx, width: rect.width, height: rect.height };
    }

    function fitBoundedCanvas(canvas, host) {
        const rect = host.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const width = Math.max(1, Math.floor(rect.width * dpr));
        const height = Math.max(1, Math.floor(rect.height * dpr));
        if (canvas.width !== width) canvas.width = width;
        if (canvas.height !== height) canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        return { ctx, width: rect.width, height: rect.height };
    }

    function startFallbackGlobe(canvas, host) {
        const nodes = Array.from({ length: 80 }, (_, i) => {
            const y = 1 - (i / 79) * 2;
            const r = Math.sqrt(1 - y * y);
            const theta = i * 2.399963229728653;
            return { x: Math.cos(theta) * r, y, z: Math.sin(theta) * r, phase: i * 0.37 };
        });
        let mouseX = 0;
        let mouseY = 0;
        let running = true;

        host.addEventListener("pointermove", event => {
            const rect = host.getBoundingClientRect();
            mouseX = (event.clientX - rect.left) / rect.width - 0.5;
            mouseY = (event.clientY - rect.top) / rect.height - 0.5;
        });

        function project(node, t, width, height) {
            const rotY = t * 0.25 + mouseX * 0.7;
            const rotX = mouseY * 0.5;
            const cosy = Math.cos(rotY);
            const siny = Math.sin(rotY);
            const cosx = Math.cos(rotX);
            const sinx = Math.sin(rotX);
            let x = node.x * cosy - node.z * siny;
            let z = node.x * siny + node.z * cosy;
            let y = node.y * cosx - z * sinx;
            z = node.y * sinx + z * cosx;
            const scale = 1.95 / (2.7 - z);
            const radius = Math.min(width, height) * 0.29;
            return {
                x: width / 2 + x * radius * scale,
                y: height / 2 + y * radius * scale,
                z,
                s: scale
            };
        }

        function animate() {
            if (!running) return;
            const { ctx, width, height } = fitCanvas(canvas, host);
            const t = performance.now() * 0.001;
            ctx.clearRect(0, 0, width, height);
            const projected = nodes.map(node => project(node, t, width, height));
            ctx.lineWidth = 1;
            for (let i = 0; i < projected.length; i += 1) {
                for (let j = i + 1; j < projected.length; j += 1) {
                    const a = projected[i];
                    const b = projected[j];
                    const dx = a.x - b.x;
                    const dy = a.y - b.y;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist < 70 && Math.abs(a.z - b.z) < 0.65) {
                        ctx.strokeStyle = `rgba(0, 212, 255, ${0.18 * Math.max(0.2, (70 - dist) / 70)})`;
                        ctx.beginPath();
                        ctx.moveTo(a.x, a.y);
                        ctx.lineTo(b.x, b.y);
                        ctx.stroke();
                    }
                }
            }
            projected.forEach((point, i) => {
                const glow = 0.45 + Math.sin(t * 2 + nodes[i].phase) * 0.2;
                ctx.fillStyle = `rgba(0, 212, 255, ${glow})`;
                ctx.shadowColor = "rgba(0, 212, 255, 0.8)";
                ctx.shadowBlur = 16;
                ctx.beginPath();
                ctx.arc(point.x, point.y, Math.max(1.8, point.s * 2.8), 0, Math.PI * 2);
                ctx.fill();
            });
            ctx.shadowBlur = 0;
            requestAnimationFrame(animate);
        }
        animate();
        return { dispose() { running = false; } };
    }

    function drawFallbackHealthRing(host, score) {
        host.innerHTML = `<canvas class="three-canvas"></canvas>`;
        const canvas = $("canvas", host);
        const { ctx, width, height } = fitCanvas(canvas, host);
        const cx = width / 2;
        const cy = height / 2;
        const radius = Math.min(width, height) * 0.34;
        const color = score >= 80 ? "#10b981" : score >= 60 ? "#f59e0b" : "#ef4444";
        ctx.clearRect(0, 0, width, height);
        ctx.lineWidth = 18;
        ctx.strokeStyle = "rgba(148,163,184,0.16)";
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.stroke();
        ctx.strokeStyle = color;
        ctx.shadowColor = color;
        ctx.shadowBlur = 22;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * (clamp(score) / 100));
        ctx.stroke();
        ctx.shadowBlur = 0;
        return { dispose() { host.innerHTML = ""; } };
    }

    function startFallbackDependencyGraph(canvas, data) {
        const stage = canvas.parentElement;
        const deps = getDependencies(data).slice(0, 70);
        const alerts = data?.dependencies?.dependabot_alerts || [];
        const vulnerable = new Set(alerts.map(alertPackage).filter(Boolean));
        let running = true;
        let hover = null;
        const tooltip = $("#graph-tooltip");

        canvas.addEventListener("pointermove", event => {
            const rect = canvas.getBoundingClientRect();
            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;
            hover = null;
            for (const node of lastNodes) {
                const dx = node.x - x;
                const dy = node.y - y;
                if (Math.sqrt(dx * dx + dy * dy) < 12) {
                    hover = node;
                    break;
                }
            }
            if (hover && tooltip) {
                tooltip.style.display = "block";
                tooltip.style.left = `${event.clientX + 14}px`;
                tooltip.style.top = `${event.clientY + 14}px`;
                tooltip.innerHTML = `<strong class="mono">${escapeHtml(hover.name)}</strong><br>${escapeHtml(hover.status)}`;
            } else if (tooltip) {
                tooltip.style.display = "none";
            }
        });
        canvas.addEventListener("pointerleave", () => { if (tooltip) tooltip.style.display = "none"; });

        let lastNodes = [];
        function animate() {
            if (!running) return;
            const { ctx, width, height } = fitCanvas(canvas, stage);
            const t = performance.now() * 0.001;
            const cx = width / 2;
            const cy = height / 2;
            ctx.clearRect(0, 0, width, height);
            lastNodes = deps.map((dep, i) => {
                const angle = (i / Math.max(1, deps.length)) * Math.PI * 2 + t * 0.12;
                const ring = Math.min(width, height) * (0.18 + (i % 4) * 0.045);
                const name = dep.name || dep.package || `dep-${i}`;
                const current = dep.version || dep.current_version || dep.constraint || "N/A";
                const isVuln = vulnerable.has(name);
                const outdated = dep.is_outdated || (dep.latest_version && String(dep.latest_version) !== String(current));
                return {
                    x: cx + Math.cos(angle) * ring,
                    y: cy + Math.sin(angle) * ring * 0.78,
                    name,
                    color: isVuln ? "#ef4444" : outdated ? "#f59e0b" : dep.is_transitive ? "#4b6b94" : "#00d4ff",
                    status: isVuln ? "Vulnerable" : outdated ? "Outdated" : dep.is_transitive ? "Transitive" : "Direct"
                };
            });
            ctx.strokeStyle = "rgba(0,212,255,0.16)";
            lastNodes.forEach((node, i) => {
                ctx.beginPath();
                ctx.moveTo(cx, cy);
                ctx.lineTo(node.x, node.y);
                ctx.stroke();
                if (lastNodes[i - 1]) {
                    ctx.beginPath();
                    ctx.moveTo(lastNodes[i - 1].x, lastNodes[i - 1].y);
                    ctx.lineTo(node.x, node.y);
                    ctx.stroke();
                }
            });
            ctx.fillStyle = "#f7fbff";
            ctx.shadowColor = "rgba(0,212,255,0.7)";
            ctx.shadowBlur = 16;
            ctx.beginPath();
            ctx.arc(cx, cy, 7, 0, Math.PI * 2);
            ctx.fill();
            lastNodes.forEach(node => {
                ctx.fillStyle = node.color;
                ctx.shadowColor = node.color;
                ctx.shadowBlur = hover === node ? 24 : 12;
                ctx.beginPath();
                ctx.arc(node.x, node.y, hover === node ? 8 : 5, 0, Math.PI * 2);
                ctx.fill();
            });
            ctx.shadowBlur = 0;
            requestAnimationFrame(animate);
        }
        animate();
        return { dispose() { running = false; } };
    }

    function disposeRenderer(key) {
        const item = state.renderers[key];
        if (item?.dispose) item.dispose();
        state.renderers[key] = null;
    }

    function renderHealthRing(score) {
        const host = $("#health-ring-scene");
        if (!host) return;
        disposeRenderer("health");
        if (!threeAvailable()) {
            state.renderers.health = drawFallbackHealthRing(host, score);
            return;
        }
        state.renderers.health = createHealthRing(host, score);
    }

    function createHealthRing(host, score) {
        host.innerHTML = "";
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(45, host.clientWidth / Math.max(1, host.clientHeight), 0.1, 100);
        camera.position.set(0, 0, 4.2);
        const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.setSize(host.clientWidth, Math.max(250, host.clientHeight), false);
        host.appendChild(renderer.domElement);

        const group = new THREE.Group();
        scene.add(group);
        scene.add(new THREE.AmbientLight(0xffffff, 1.6));
        const point = new THREE.PointLight(0x00d4ff, 2.1, 10);
        point.position.set(2, 2, 4);
        scene.add(point);

        const pct = clamp(score) / 100;
        const base = new THREE.Mesh(
            new THREE.TorusGeometry(1.18, 0.08, 20, 120),
            new THREE.MeshStandardMaterial({ color: 0x253247, roughness: 0.4, metalness: 0.2 })
        );
        const color = score >= 80 ? 0x10b981 : score >= 60 ? 0xf59e0b : 0xef4444;
        const arc = new THREE.Mesh(
            new THREE.TorusGeometry(1.18, 0.115, 20, 160, Math.PI * 2 * Math.max(0.02, pct)),
            new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.35, roughness: 0.25, metalness: 0.35 })
        );
        arc.rotation.z = -Math.PI / 2;
        group.add(base, arc);

        let running = true;
        function animate() {
            if (!running) return;
            group.rotation.y += 0.006;
            group.rotation.x = Math.sin(performance.now() * 0.001) * 0.08;
            renderer.render(scene, camera);
            requestAnimationFrame(animate);
        }
        animate();

        return {
            dispose() {
                running = false;
                renderer.dispose();
                host.innerHTML = "";
            }
        };
    }

    function renderDependencyGraph(data) {
        const canvas = $("#dependency-graph-canvas");
        if (!canvas) return;
        if (!canvas.offsetParent && state.activeTab !== "deps") return;
        disposeRenderer("deps");
        if (!threeAvailable()) {
            state.renderers.deps = startFallbackDependencyGraph(canvas, data);
            return;
        }
        state.renderers.deps = createDependencyGraph(canvas, data);
    }

    function createDependencyGraph(canvas, data) {
        const stage = canvas.parentElement;
        const deps = getDependencies(data).slice(0, 80);
        const alerts = data?.dependencies?.dependabot_alerts || [];
        const vulnerable = new Set(alerts.map(alertPackage).filter(Boolean));

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(55, stage.clientWidth / Math.max(1, stage.clientHeight), 0.1, 100);
        camera.position.set(0, 0, 9);
        const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.setSize(stage.clientWidth, stage.clientHeight, false);
        scene.add(new THREE.AmbientLight(0xffffff, 1.15));
        const light = new THREE.PointLight(0x00d4ff, 2, 22);
        light.position.set(3, 4, 7);
        scene.add(light);

        const group = new THREE.Group();
        scene.add(group);
        const nodes = [];
        const materialCache = new Map();

        function mat(color, emissive = 0.15) {
            const key = `${color}-${emissive}`;
            if (!materialCache.has(key)) {
                materialCache.set(key, new THREE.MeshStandardMaterial({
                    color,
                    emissive: color,
                    emissiveIntensity: emissive,
                    roughness: 0.32,
                    metalness: 0.18
                }));
            }
            return materialCache.get(key);
        }

        deps.forEach((dep, index) => {
            const name = dep.name || dep.package || `dep-${index}`;
            const angle = (index / Math.max(1, deps.length)) * Math.PI * 2;
            const ring = 2.2 + (index % 4) * 0.72;
            const z = ((index % 9) - 4) * 0.17;
            const isVuln = vulnerable.has(name);
            const outdated = dep.is_outdated || (dep.latest_version && (dep.version || dep.current_version || dep.constraint) && String(dep.latest_version) !== String(dep.version || dep.current_version || dep.constraint));
            const direct = !dep.is_transitive;
            const color = isVuln ? 0xef4444 : outdated ? 0xf59e0b : direct ? 0x00d4ff : 0x4b6b94;
            const mesh = new THREE.Mesh(new THREE.SphereGeometry(isVuln ? 0.105 : 0.085, 18, 18), mat(color, isVuln ? 0.65 : 0.2));
            mesh.position.set(Math.cos(angle) * ring, Math.sin(angle) * ring, z);
            mesh.userData = { name, direct, vulnerable: isVuln, outdated, version: dep.version || dep.current_version || dep.constraint || "N/A" };
            group.add(mesh);
            nodes.push(mesh);
        });

        const linePoints = [];
        nodes.forEach((node, index) => {
            if (index % 2 === 0) {
                linePoints.push(new THREE.Vector3(0, 0, 0), node.position.clone());
            } else if (nodes[index - 1]) {
                linePoints.push(nodes[index - 1].position.clone(), node.position.clone());
            }
        });
        const lineGeo = new THREE.BufferGeometry().setFromPoints(linePoints);
        const lines = new THREE.LineSegments(lineGeo, new THREE.LineBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.18 }));
        group.add(lines);

        const center = new THREE.Mesh(new THREE.SphereGeometry(0.18, 24, 24), mat(0xffffff, 0.18));
        group.add(center);

        const raycaster = new THREE.Raycaster();
        const pointer = new THREE.Vector2();
        const tooltip = $("#graph-tooltip");

        function onMove(event) {
            const rect = canvas.getBoundingClientRect();
            pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
            pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
            raycaster.setFromCamera(pointer, camera);
            const hit = raycaster.intersectObjects(nodes)[0];
            if (hit && tooltip) {
                const data = hit.object.userData;
                tooltip.style.display = "block";
                tooltip.style.left = `${event.clientX + 14}px`;
                tooltip.style.top = `${event.clientY + 14}px`;
                tooltip.innerHTML = `<strong class="mono">${escapeHtml(data.name)}</strong><br>version ${escapeHtml(data.version)}<br>${data.vulnerable ? "Vulnerable" : data.outdated ? "Outdated" : data.direct ? "Direct dependency" : "Transitive dependency"}`;
            } else if (tooltip) {
                tooltip.style.display = "none";
            }
        }
        canvas.addEventListener("pointermove", onMove);
        canvas.addEventListener("pointerleave", () => { if (tooltip) tooltip.style.display = "none"; });

        let running = true;
        function animate() {
            if (!running) return;
            group.rotation.y += 0.004;
            group.rotation.x = Math.sin(performance.now() * 0.0007) * 0.12;
            renderer.render(scene, camera);
            requestAnimationFrame(animate);
        }
        animate();

        return {
            dispose() {
                running = false;
                canvas.removeEventListener("pointermove", onMove);
                renderer.dispose();
            }
        };
    }

    function initRepoGlobe() {
        const canvas = $("#repo-globe-canvas");
        const card = $("#repo-globe-card");
        if (!canvas || !card) return;
        if (!threeAvailable()) {
            state.renderers.globe = startFallbackGlobe(canvas, card);
            return;
        }
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(52, card.clientWidth / Math.max(1, card.clientHeight), 0.1, 100);
        camera.position.set(0, 0, 7.2);
        const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.setSize(card.clientWidth, card.clientHeight, false);
        scene.add(new THREE.AmbientLight(0xffffff, 1.2));
        const light = new THREE.PointLight(0x00d4ff, 2.4, 18);
        light.position.set(4, 4, 7);
        scene.add(light);

        const group = new THREE.Group();
        scene.add(group);

        const nodeMaterial = new THREE.MeshStandardMaterial({
            color: 0x00d4ff,
            emissive: 0x00d4ff,
            emissiveIntensity: 0.55,
            roughness: 0.24,
            metalness: 0.2
        });
        const points = [];
        for (let i = 0; i < 80; i += 1) {
            const y = 1 - (i / 79) * 2;
            const radius = Math.sqrt(1 - y * y);
            const theta = i * 2.399963229728653;
            const pos = new THREE.Vector3(Math.cos(theta) * radius * 2.35, y * 2.35, Math.sin(theta) * radius * 2.35);
            points.push(pos);
            const node = new THREE.Mesh(new THREE.SphereGeometry(0.035 + (i % 5) * 0.007, 12, 12), nodeMaterial);
            node.position.copy(pos);
            group.add(node);
        }
        const linePoints = [];
        for (let i = 0; i < points.length; i += 1) {
            for (let j = i + 1; j < points.length; j += 1) {
                if (points[i].distanceTo(points[j]) < 0.78 && linePoints.length < 520) {
                    linePoints.push(points[i], points[j]);
                }
            }
        }
        group.add(new THREE.LineSegments(
            new THREE.BufferGeometry().setFromPoints(linePoints),
            new THREE.LineBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.22 })
        ));

        let mouseX = 0;
        let mouseY = 0;
        card.addEventListener("pointermove", event => {
            const rect = card.getBoundingClientRect();
            mouseX = ((event.clientX - rect.left) / rect.width - 0.5) * 0.32;
            mouseY = ((event.clientY - rect.top) / rect.height - 0.5) * 0.32;
        });

        let running = true;
        function animate() {
            if (!running) return;
            const t = performance.now() * 0.001;
            group.rotation.y += 0.0035;
            group.rotation.x += (mouseY - group.rotation.x) * 0.035;
            group.rotation.z += (mouseX - group.rotation.z) * 0.035;
            group.scale.setScalar(1 + Math.sin(t * 1.8) * 0.018);
            renderer.render(scene, camera);
            requestAnimationFrame(animate);
        }
        animate();
        state.renderers.globe = {
            dispose() {
                running = false;
                renderer.dispose();
            }
        };
    }

    function startFallbackHomeScene(canvas, host) {
        let running = true;
        let pointerX = 0;
        let pointerY = 0;
        const nodes = Array.from({ length: 46 }, (_, index) => ({
            angle: index * 0.82,
            radius: 44 + (index % 5) * 18,
            orbit: 0.18 + (index % 7) * 0.018,
            depth: ((index % 9) - 4) * 6
        }));

        function onMove(event) {
            const rect = host.getBoundingClientRect();
            pointerX = ((event.clientX - rect.left) / Math.max(1, rect.width) - 0.5) * 28;
            pointerY = ((event.clientY - rect.top) / Math.max(1, rect.height) - 0.5) * 20;
        }

        host.addEventListener("pointermove", onMove);

        function animate() {
            if (!running) return;
            const { ctx, width, height } = fitBoundedCanvas(canvas, host);
            const cx = width / 2 + pointerX;
            const cy = height / 2 + pointerY;
            const time = performance.now() * 0.001;
            ctx.clearRect(0, 0, width, height);

            const points = nodes.map(node => {
                const a = node.angle + time * node.orbit;
                const x = cx + Math.cos(a) * node.radius * (1 + node.depth / 120);
                const y = cy + Math.sin(a * 1.18) * node.radius * 0.72;
                return { x, y, depth: node.depth };
            });

            ctx.lineWidth = 1;
            points.forEach((point, index) => {
                points.slice(index + 1, index + 4).forEach(next => {
                    ctx.strokeStyle = "rgba(0, 212, 255, 0.16)";
                    ctx.beginPath();
                    ctx.moveTo(point.x, point.y);
                    ctx.lineTo(next.x, next.y);
                    ctx.stroke();
                });
            });

            ctx.strokeStyle = "rgba(0, 212, 255, 0.35)";
            ctx.lineWidth = 1.4;
            ctx.beginPath();
            ctx.ellipse(cx, cy, 108, 52, time * 0.18, 0, Math.PI * 2);
            ctx.stroke();
            ctx.beginPath();
            ctx.ellipse(cx, cy, 72, 150, -time * 0.13, 0, Math.PI * 2);
            ctx.stroke();

            points.forEach(point => {
                const radius = 3.5 + Math.max(0, point.depth) / 18;
                ctx.fillStyle = "rgba(0, 212, 255, 0.86)";
                ctx.shadowColor = "rgba(0, 212, 255, 0.8)";
                ctx.shadowBlur = 14;
                ctx.beginPath();
                ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
                ctx.fill();
            });
            ctx.shadowBlur = 0;
            ctx.fillStyle = "rgba(247, 251, 255, 0.96)";
            ctx.beginPath();
            ctx.arc(cx, cy, 9, 0, Math.PI * 2);
            ctx.fill();
            requestAnimationFrame(animate);
        }

        animate();
        return {
            dispose() {
                running = false;
                host.removeEventListener("pointermove", onMove);
            }
        };
    }

    function initHomeScene() {
        const canvas = $("#home-constellation-canvas");
        const host = $("#home-visual");
        if (!canvas || !host || host.offsetParent === null) return;
        disposeRenderer("home");
        if (!threeAvailable()) {
            state.renderers.home = startFallbackHomeScene(canvas, host);
            return;
        }

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 100);
        camera.position.set(0, 0, 7.4);
        const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

        const group = new THREE.Group();
        scene.add(group);
        scene.add(new THREE.AmbientLight(0xffffff, 1.1));
        const keyLight = new THREE.PointLight(0x00d4ff, 2.6, 18);
        keyLight.position.set(2.8, 3.4, 6.5);
        scene.add(keyLight);
        const fillLight = new THREE.PointLight(0x7c3aed, 1.15, 16);
        fillLight.position.set(-3.4, -2.6, 5.2);
        scene.add(fillLight);

        const nodeMaterial = new THREE.MeshStandardMaterial({
            color: 0x00d4ff,
            emissive: 0x00d4ff,
            emissiveIntensity: 0.42,
            roughness: 0.28,
            metalness: 0.18
        });
        const mutedMaterial = new THREE.MeshStandardMaterial({
            color: 0x4b6b94,
            emissive: 0x1f5f86,
            emissiveIntensity: 0.16,
            roughness: 0.36,
            metalness: 0.12
        });
        const core = new THREE.Mesh(
            new THREE.IcosahedronGeometry(0.42, 1),
            new THREE.MeshStandardMaterial({
                color: 0xf7fbff,
                emissive: 0x00d4ff,
                emissiveIntensity: 0.18,
                roughness: 0.22,
                metalness: 0.38
            })
        );
        group.add(core);

        const nodes = [];
        for (let i = 0; i < 52; i += 1) {
            const ring = 1.2 + (i % 4) * 0.44;
            const angle = i * 2.399963229728653;
            const y = ((i % 13) - 6) * 0.16;
            const z = Math.sin(i * 0.72) * 1.25;
            const node = new THREE.Mesh(
                new THREE.SphereGeometry(i % 9 === 0 ? 0.082 : 0.055, 16, 16),
                i % 5 === 0 ? mutedMaterial : nodeMaterial
            );
            node.position.set(Math.cos(angle) * ring, y, Math.sin(angle) * ring * 0.78 + z * 0.25);
            nodes.push(node);
            group.add(node);
        }

        const linePoints = [];
        nodes.forEach((node, index) => {
            linePoints.push(new THREE.Vector3(0, 0, 0), node.position.clone());
            const next = nodes[(index + 7) % nodes.length];
            if (index % 2 === 0) linePoints.push(node.position.clone(), next.position.clone());
        });
        const lines = new THREE.LineSegments(
            new THREE.BufferGeometry().setFromPoints(linePoints),
            new THREE.LineBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.2 })
        );
        group.add(lines);

        const torusOne = new THREE.Mesh(
            new THREE.TorusGeometry(2.15, 0.01, 8, 128),
            new THREE.MeshBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.42 })
        );
        const torusTwo = torusOne.clone();
        torusTwo.rotation.x = Math.PI / 2.6;
        torusTwo.rotation.y = Math.PI / 4;
        group.add(torusOne, torusTwo);

        const target = { x: 0, y: 0 };
        function onMove(event) {
            const rect = host.getBoundingClientRect();
            target.x = ((event.clientX - rect.left) / Math.max(1, rect.width) - 0.5) * 0.42;
            target.y = ((event.clientY - rect.top) / Math.max(1, rect.height) - 0.5) * 0.32;
        }
        host.addEventListener("pointermove", onMove);

        function resize() {
            const width = Math.max(1, host.clientWidth);
            const height = Math.max(1, host.clientHeight);
            camera.aspect = width / height;
            camera.updateProjectionMatrix();
            renderer.setSize(width, height, false);
        }
        resize();
        const observer = new ResizeObserver(resize);
        observer.observe(host);

        let running = true;
        function animate() {
            if (!running) return;
            const time = performance.now() * 0.001;
            group.rotation.y += 0.0026;
            group.rotation.x += (target.y - group.rotation.x) * 0.045;
            group.rotation.z += (target.x - group.rotation.z) * 0.04;
            core.scale.setScalar(1 + Math.sin(time * 2.1) * 0.045);
            torusOne.rotation.z += 0.004;
            torusTwo.rotation.y += 0.003;
            nodes.forEach((node, index) => {
                node.scale.setScalar(1 + Math.sin(time * 2.4 + index) * 0.08);
            });
            renderer.render(scene, camera);
            requestAnimationFrame(animate);
        }
        animate();

        state.renderers.home = {
            dispose() {
                running = false;
                host.removeEventListener("pointermove", onMove);
                observer.disconnect();
                scene.traverse(item => {
                    if (item.geometry) item.geometry.dispose();
                    if (item.material) {
                        if (Array.isArray(item.material)) item.material.forEach(material => material.dispose());
                        else item.material.dispose();
                    }
                });
                renderer.dispose();
            }
        };
    }

    function init() {
        initTheme();
        initTabs();
        initTypewriter();
        initLanding();
        initAnalyzeForm();
        initBatch();
        loadAuthStatus();
        refreshRateLimit();
        loadHistory();
        setInterval(refreshRateLimit, 120000);
        renderOverview(null);
        renderCicd(null);
        renderDeps(null);
    }

    document.addEventListener("DOMContentLoaded", init);
})();
