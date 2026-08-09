(() => {
  const TOKEN_STORAGE_KEY = "company-rag-access-token";

  const analyticsView = document.querySelector("#analytics-view");
  const filtersForm = document.querySelector("#analytics-filters");
  const refreshButton = document.querySelector("#analytics-refresh");
  const statusMessage = document.querySelector("#analytics-status-message");
  const analyticsTabs = document.querySelectorAll("[data-analytics-tab]");
  const analyticsPanels = document.querySelectorAll("[data-analytics-panel]");

  const elements = {
    totalQuestions: document.querySelector("#metric-total-questions"),
    averageLatency: document.querySelector("#metric-average-latency"),
    averageRating: document.querySelector("#metric-average-rating"),
    badRate: document.querySelector("#metric-bad-rate"),
    goodRate: document.querySelector("#metric-good-rate"),
    feedbackCount: document.querySelector("#metric-feedback-count"),
    feedbackTotal: document.querySelector("#feedback-total"),
    feedbackAverage: document.querySelector("#feedback-average"),
    feedbackBadRate: document.querySelector("#feedback-bad-rate"),
    feedbackGoodRate: document.querySelector("#feedback-good-rate"),
    ratingDistribution: document.querySelector("#rating-distribution"),
    retrievalDistribution: document.querySelector("#retrieval-distribution"),
    failedDocumentsTable: document.querySelector("#failed-documents-table"),
  };

  let hasLoadedAnalytics = false;

  if (!analyticsView || !filtersForm) {
    return;
  }

  analyticsTabs.forEach((button) => {
    button.addEventListener("click", () => {
      switchAnalyticsTab(button.dataset.analyticsTab);
    });
  });

  filtersForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshAnalytics();
  });

  window.addEventListener("company-rag-auth-change", (event) => {
    const isAuthenticated = Boolean(event.detail?.isAuthenticated);
    setFilterState(isAuthenticated);
    if (!isAuthenticated) {
      hasLoadedAnalytics = false;
      renderSignedOutState();
    }
  });

  window.addEventListener("company-rag-view-change", async (event) => {
    if (event.detail?.view === "analytics-view" && !hasLoadedAnalytics) {
      await refreshAnalytics();
    }
  });

  setFilterState(Boolean(getAccessToken()));
  renderSignedOutState();

  async function refreshAnalytics() {
    const token = getAccessToken();
    if (!token) {
      renderSignedOutState();
      return;
    }

    setLoading(true);
    setStatus("Loading analytics...");

    try {
      const queryString = buildQueryString();
      const [summary, feedback, retrieval] = await Promise.all([
        fetchAnalytics(`/api/analytics/summary${queryString}`, token),
        fetchAnalytics(`/api/analytics/feedback${queryString}`, token),
        fetchAnalytics(`/api/analytics/retrieval${queryString}`, token),
      ]);

      renderSummary(summary);
      renderFeedback(feedback);
      renderRetrieval(retrieval);
      hasLoadedAnalytics = true;
      setStatus(`Updated ${new Date().toLocaleTimeString()}`);
    } catch (error) {
      setStatus(error.message || "Analytics request failed.", true);
    } finally {
      setLoading(false);
    }
  }

  async function fetchAnalytics(path, token) {
    const response = await fetch(path, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    const payload = await readJson(response);

    if (response.status === 401) {
      window.companyRagAuth?.clearSession();
      throw new Error("Session expired. Log in again.");
    }

    if (!response.ok) {
      throw new Error(payload.detail || "Analytics request failed.");
    }

    return payload;
  }

  function buildQueryString() {
    const formData = new FormData(filtersForm);
    const params = new URLSearchParams();

    for (const [key, value] of formData.entries()) {
      const trimmedValue = String(value).trim();
      if (trimmedValue) {
        params.set(key, trimmedValue);
      }
    }

    return params.toString() ? `?${params.toString()}` : "";
  }

  function renderSummary(summary) {
    setText(elements.totalQuestions, formatNumber(summary.total_questions));
    setText(elements.averageLatency, formatMs(summary.average_latency_ms));
    setText(elements.averageRating, formatRating(summary.average_user_rating));
    setText(elements.badRate, formatRate(summary.bad_answer_rate));
    setText(elements.goodRate, formatRate(summary.good_answer_rate));
    setText(elements.feedbackCount, formatNumber(summary.feedback_count));
  }

  function renderFeedback(feedback) {
    setText(elements.feedbackTotal, formatNumber(feedback.feedback_count));
    setText(elements.feedbackAverage, formatRating(feedback.average_user_rating));
    setText(elements.feedbackBadRate, formatRate(feedback.bad_answer_rate));
    setText(elements.feedbackGoodRate, formatRate(feedback.good_answer_rate));

    const distribution = normalizeRatingDistribution(feedback.rating_distribution);
    const maxCount = Math.max(...distribution.map((item) => item.count), 1);
    elements.ratingDistribution.replaceChildren(
      ...distribution.map((item) =>
        buildBarRow({
          label: `${item.rating} star`,
          count: item.count,
          value: formatRate(item.rate),
          width: `${(item.count / maxCount) * 100}%`,
        })
      )
    );
  }

  function renderRetrieval(retrieval) {
    const modeItems = retrieval.retrieval_mode_distribution || [];
    if (!modeItems.length) {
      elements.retrievalDistribution.replaceChildren(
        buildEmptyBlock("No retrieval analytics yet.")
      );
    } else {
      elements.retrievalDistribution.replaceChildren(
        ...modeItems.map((item) =>
          buildModeRow({
            label: titleCase(item.retrieval_mode),
            count: item.count,
            rate: formatRate(item.rate),
            latency: formatMs(item.average_latency_ms),
            width: `${Math.max((item.rate || 0) * 100, item.count ? 6 : 0)}%`,
          })
        )
      );
    }

    renderFailedDocuments(retrieval.top_failed_documents || []);
  }

  function renderFailedDocuments(documents) {
    if (!documents.length) {
      elements.failedDocumentsTable.replaceChildren(
        buildTableRow(["No failed document data yet."], 3)
      );
      return;
    }

    elements.failedDocumentsTable.replaceChildren(
      ...documents.map((document) =>
        buildTableRow([
          document.filename || document.source_path || "Unknown source",
          formatNumber(document.failure_count),
          formatScore(document.average_retrieval_score),
        ])
      )
    );
  }

  function renderSignedOutState() {
    setStatus("Log in to view analytics.");
    renderSummary({
      total_questions: null,
      average_latency_ms: null,
      average_user_rating: null,
      bad_answer_rate: null,
      good_answer_rate: null,
      feedback_count: null,
    });
    renderFeedback({
      feedback_count: null,
      average_user_rating: null,
      bad_answer_rate: null,
      good_answer_rate: null,
      rating_distribution: [],
    });
    elements.retrievalDistribution.replaceChildren(
      buildEmptyBlock("Log in to view analytics.")
    );
    elements.failedDocumentsTable.replaceChildren(
      buildTableRow(["Log in to view analytics."], 3)
    );
  }

  function switchAnalyticsTab(target) {
    if (!target) {
      return;
    }

    analyticsTabs.forEach((button) => {
      const isActive = button.dataset.analyticsTab === target;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-selected", String(isActive));
    });

    analyticsPanels.forEach((panel) => {
      const isActive = panel.dataset.analyticsPanel === target;
      panel.hidden = !isActive;
      panel.classList.toggle("is-active", isActive);
    });
  }

  function buildBarRow({ label, count, value, width }) {
    const row = document.createElement("div");
    row.className = "bar-row";

    const header = document.createElement("div");
    header.className = "bar-row-header";

    const labelElement = document.createElement("span");
    labelElement.textContent = label;

    const valueElement = document.createElement("span");
    valueElement.textContent = `${formatNumber(count)} (${value})`;

    const track = document.createElement("div");
    track.className = "bar-track";

    const fill = document.createElement("div");
    fill.className = "bar-fill";
    fill.style.width = width;

    header.append(labelElement, valueElement);
    track.append(fill);
    row.append(header, track);
    return row;
  }

  function buildModeRow({ label, count, rate, latency, width }) {
    const row = document.createElement("div");
    row.className = "mode-row";

    const header = document.createElement("div");
    header.className = "mode-row-header";

    const name = document.createElement("strong");
    name.textContent = label;

    const details = document.createElement("span");
    details.textContent = `${formatNumber(count)} requests / ${rate} / ${latency}`;

    const track = document.createElement("div");
    track.className = "bar-track";

    const fill = document.createElement("div");
    fill.className = "bar-fill secondary";
    fill.style.width = width;

    header.append(name, details);
    track.append(fill);
    row.append(header, track);
    return row;
  }

  function buildTableRow(values, colspan = 1) {
    const row = document.createElement("tr");

    if (values.length === 1 && colspan > 1) {
      const cell = document.createElement("td");
      cell.colSpan = colspan;
      cell.textContent = values[0];
      row.append(cell);
      return row;
    }

    values.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    });

    return row;
  }

  function buildEmptyBlock(message) {
    const block = document.createElement("div");
    block.className = "empty-block";
    block.textContent = message;
    return block;
  }

  function normalizeRatingDistribution(distribution = []) {
    const byRating = new Map(
      distribution.map((item) => [Number(item.rating), item])
    );
    return [1, 2, 3, 4, 5].map((rating) => {
      const item = byRating.get(rating) || {};
      return {
        rating,
        count: Number(item.count) || 0,
        rate: Number.isFinite(Number(item.rate)) ? Number(item.rate) : null,
      };
    });
  }

  async function readJson(response) {
    try {
      return await response.json();
    } catch {
      return {};
    }
  }

  function getAccessToken() {
    return (
      window.companyRagAuth?.getAccessToken() ||
      localStorage.getItem(TOKEN_STORAGE_KEY) ||
      ""
    );
  }

  function setLoading(isLoading) {
    refreshButton.disabled = isLoading || !getAccessToken();
    refreshButton.textContent = isLoading ? "Refreshing" : "Refresh";
    setFilterState(Boolean(getAccessToken()) && !isLoading);
  }

  function setFilterState(isEnabled) {
    const fields = filtersForm.querySelectorAll("input, select, button");
    fields.forEach((field) => {
      field.disabled = !isEnabled;
    });
  }

  function setStatus(message, isError = false) {
    statusMessage.textContent = message;
    statusMessage.classList.toggle("is-error", isError);
  }

  function setText(element, text) {
    if (element) {
      element.textContent = text;
    }
  }

  function formatNumber(value) {
    if (isMissing(value)) {
      return "--";
    }

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
      return "--";
    }

    return new Intl.NumberFormat().format(numericValue);
  }

  function formatMs(value) {
    if (isMissing(value)) {
      return "--";
    }

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
      return "--";
    }

    if (numericValue >= 1000) {
      return `${(numericValue / 1000).toFixed(2)} s`;
    }

    return `${numericValue.toFixed(0)} ms`;
  }

  function formatRating(value) {
    if (isMissing(value)) {
      return "--";
    }

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
      return "--";
    }

    return numericValue.toFixed(2);
  }

  function formatRate(value) {
    if (isMissing(value)) {
      return "--";
    }

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
      return "--";
    }

    return `${(numericValue * 100).toFixed(1)}%`;
  }

  function formatScore(value) {
    if (isMissing(value)) {
      return "--";
    }

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
      return "--";
    }

    return numericValue.toFixed(4);
  }

  function titleCase(value) {
    return String(value || "")
      .replace(/[_-]/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function isMissing(value) {
    return value === null || value === undefined || value === "";
  }
})();
