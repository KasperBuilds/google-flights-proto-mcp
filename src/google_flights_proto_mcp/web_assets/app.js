const state = { payload: null, filter: "all" };

const euro = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

const dateTime = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Lisbon",
  timeZoneName: "short",
});

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function statusClass(status) {
  if (status === "DEAL") return "deal";
  if (status === "BELOW MEDIAN") return "below";
  return "hold";
}

function friendlyStatus(status) {
  if (status === "DEAL") return "Deal";
  if (status === "BELOW MEDIAN") return "Below median";
  return "Watch";
}

function formatChecked(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : dateTime.format(parsed);
}

function makeChip(text, preferred = false) {
  return element("span", `chip${preferred ? " preferred" : ""}`, text);
}

function makeCard(option) {
  const card = element("article", `flight-card${option.rank === 1 ? " rank-one" : ""}`);
  card.dataset.status = option.status;
  card.dataset.direct = option.stops === 0 ? "true" : "false";

  const top = element("div", "card-top");
  const titleWrap = element("div");
  titleWrap.append(
    element("span", "option-label", `Option ${option.rank}`),
    element("h3", "destination", option.destination),
  );
  const identity = element("div", "identity-badges");
  if (option.on_bucket_list) identity.append(element("span", "bucket-badge", "★ Bucket list"));
  identity.append(element("span", "airport", option.airport));
  top.append(titleWrap, identity);

  const fareRow = element("div", "fare-row");
  const fare = element("div", "fare");
  fare.append(document.createTextNode(euro.format(option.price)), element("small", "", " return"));
  fareRow.append(fare, element("span", `status-pill ${statusClass(option.status)}`, friendlyStatus(option.status)));

  const comparison = element("div", "comparison");
  const comparisonText = element("div", "comparison-text");
  const percent = Math.round(option.percent_below_median * 100);
  comparisonText.append(
    element("span", "", percent >= 0 ? `${percent}% below median` : `${Math.abs(percent)}% above median`),
    element("span", "", `median ${euro.format(option.median)}`),
  );
  const track = element("div", "comparison-track");
  const fill = element("div", `comparison-fill${percent < 0 ? " over" : ""}`);
  fill.style.width = `${Math.max(8, Math.min(100, (option.price / option.median) * 100))}%`;
  track.append(fill);
  comparison.append(comparisonText, track);

  const detail = element("p", "flight-detail", option.outbound_example);
  const chips = element("div", "chips");
  option.bucket_list_labels.forEach((label) => {
    chips.append(makeChip(`Bucket: ${label.name} (${label.type})`, true));
  });
  const bucketNames = new Set(option.bucket_list_labels.map((label) => label.name));
  option.categories
    .filter((category) => !bucketNames.has(category))
    .slice(0, 3)
    .forEach((category) => chips.append(makeChip(category)));
  if (option.preferred_timing_categories.length) chips.append(makeChip("Right season", true));
  chips.append(makeChip(option.stops === 0 ? "Direct" : `${option.stops} stop`));

  const action = element("div", "card-action");
  const checked = element("span", "checked", `Quoted ${formatChecked(option.checked_at)}`);
  const link = element("a", "google-link", "Check on Google ↗");
  link.href = option.search_url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  action.append(checked, link);

  card.append(top, fareRow, comparison, detail, chips, action);
  return card;
}

function matchesFilter(option) {
  if (state.filter === "bucket") return option.on_bucket_list;
  if (state.filter === "below") return option.percent_below_median > 0;
  if (state.filter === "direct") return option.stops === 0;
  return true;
}

function renderWeekends() {
  const container = document.querySelector("#weekends");
  container.replaceChildren();
  let visibleSections = 0;

  state.payload.weekends.forEach((weekend, index) => {
    const matches = weekend.options.filter(matchesFilter);
    if (!matches.length && state.filter !== "all") return;
    visibleSections += 1;
    const section = element("section", "weekend-section");
    section.id = `weekend-${index + 1}`;
    const heading = element("div", "weekend-heading");
    heading.append(
      element("h2", "", weekend.label),
      element("p", "", `${matches.length} option${matches.length === 1 ? "" : "s"} shown`),
    );
    const grid = element("div", matches.length ? "flight-grid" : "empty-filter");
    if (matches.length) {
      matches.forEach((option) => grid.append(makeCard(option)));
    } else {
      grid.textContent = `No realistic return fare under ${euro.format(state.payload.summary.max_return_price)} was found for this weekend.`;
    }
    section.append(heading, grid);
    container.append(section);
  });

  if (!visibleSections) {
    container.append(element("div", "empty-filter", "No options match this filter."));
  }
  container.setAttribute("aria-busy", "false");
}

function renderSummary(refresh) {
  const summary = state.payload.summary;
  document.querySelector("#stat-below").textContent = `${summary.below_median}/${summary.options}`;
  document.querySelector("#stat-below-note").textContent = `of ${summary.options} fares under ${euro.format(summary.max_return_price)}`;
  document.querySelector("#hero-weekends").textContent = summary.weekends;
  document.querySelector("#hero-options").textContent = summary.options;
  if (summary.best_saving) {
    document.querySelector("#stat-saving").textContent = `${Math.round(summary.best_saving.percent * 100)}%`;
    document.querySelector("#stat-saving-place").textContent = `${summary.best_saving.destination} · ${summary.best_saving.weekend}`;
  } else {
    document.querySelector("#stat-saving").textContent = "—";
    document.querySelector("#stat-saving-place").textContent = "No eligible fares found";
  }
  document.querySelector("#stat-updated").textContent = formatChecked(state.payload.generated_at);
  document.querySelector("#stat-age").textContent = "Per-row quote times shown below";

  const live = document.querySelector("#live-status");
  live.className = "live-status ready";
  if (refresh.running) {
    live.querySelector("span:last-child").textContent = "Refreshing prices now";
  } else if (refresh.last_error) {
    live.className = "live-status error";
    live.querySelector("span:last-child").textContent = "Last refresh failed · showing saved data";
  } else {
    live.querySelector("span:last-child").textContent = "Hourly price refresh active";
  }
}

function populateJump() {
  const select = document.querySelector("#weekend-select");
  select.replaceChildren(element("option", "", "Choose a weekend"));
  select.options[0].value = "";
  state.payload.weekends.forEach((weekend, index) => {
    const option = element("option", "", weekend.label);
    option.value = `weekend-${index + 1}`;
    select.append(option);
  });
  select.disabled = false;
}

async function loadDeals() {
  const errorPanel = document.querySelector("#error-panel");
  errorPanel.hidden = true;
  try {
    const response = await fetch("/api/deals", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`The server returned ${response.status}.`);
    const result = await response.json();
    state.payload = result.data;
    renderSummary(result.refresh);
    populateJump();
    renderWeekends();
  } catch (error) {
    document.querySelector("#live-status").className = "live-status error";
    document.querySelector("#live-status span:last-child").textContent = "Snapshot unavailable";
    document.querySelector("#error-message").textContent = error.message;
    errorPanel.hidden = false;
    document.querySelector("#weekends").setAttribute("aria-busy", "false");
  }
}

document.querySelectorAll(".filter-button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".filter-button").forEach((candidate) => candidate.classList.remove("active"));
    button.classList.add("active");
    state.filter = button.dataset.filter;
    if (state.payload) renderWeekends();
  });
});

document.querySelector("#weekend-select").addEventListener("change", (event) => {
  if (!event.target.value) return;
  document.getElementById(event.target.value)?.scrollIntoView({ behavior: "smooth", block: "start" });
});

document.querySelector("#retry-button").addEventListener("click", loadDeals);

loadDeals();
window.setInterval(loadDeals, 60_000);
