const state = {
  payload: null,
  filter: "all",
  view: "top",
  expandedWeekends: new Set(),
  collapsedWeekends: new Set(),
};

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

function friendlyStatus(status) {
  if (status === "DEAL") return "Deal";
  if (status === "BELOW MEDIAN") return "Below median";
  return "Watch";
}

function statusClass(status) {
  if (status === "DEAL") return "deal";
  if (status === "BELOW MEDIAN") return "below";
  return "watch";
}

function formatChecked(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : dateTime.format(parsed);
}

function makeTag(text, className = "") {
  return element("span", `tag${className ? ` ${className}` : ""}`, text);
}

function makeFareRow(option) {
  const row = element("article", `flight-row${option.rank === 1 ? " top-pick" : ""}`);
  row.dataset.status = option.status;
  row.dataset.direct = option.stops === 0 ? "true" : "false";

  const destination = element("div", "destination-cell");
  const destinationTitle = element("div", "destination-title");
  destinationTitle.append(
    element("span", "rank", `${option.rank}`),
    element("h3", "destination", option.destination),
    element("span", "airport", option.airport),
  );
  destination.append(destinationTitle);

  if (option.on_bucket_list) {
    const names = option.bucket_list_labels.map((label) => label.name).join(" · ");
    destination.append(element("div", "bucket-label", `Bucket list · ${names}`));
  }

  const tags = element("div", "tags");
  const bucketNames = new Set(option.bucket_list_labels.map((label) => label.name));
  option.categories
    .filter((category) => !bucketNames.has(category))
    .slice(0, 2)
    .forEach((category) => tags.append(makeTag(category)));
  if (option.preferred_timing_categories.length) tags.append(makeTag("Right season", "season"));
  if (tags.children.length) destination.append(tags);

  const flight = element("div", "flight-cell");
  flight.append(
    element("span", "mobile-label", "Outbound"),
    element("strong", "flight-example", option.outbound_example),
    element("span", "flight-meta", option.stops === 0 ? "Direct" : `${option.stops} stop`),
  );

  const price = element("div", "price-cell");
  price.append(
    element("span", "mobile-label", "Return fare"),
    element("strong", "fare", euro.format(option.price)),
    element("span", `status ${statusClass(option.status)}`, friendlyStatus(option.status)),
  );

  const comparison = element("div", "comparison-cell");
  const percent = Math.round(option.percent_below_median * 100);
  const comparisonText = percent > 0
    ? `${percent}% below`
    : percent < 0
      ? `${Math.abs(percent)}% above`
      : "At median";
  comparison.append(
    element("span", "mobile-label", "Compared with median"),
    element("strong", percent > 0 ? "saving" : "", comparisonText),
    element("span", "median", `${euro.format(option.median)} median`),
  );

  const action = element("div", "action-cell");
  const link = element("a", "google-link", "View flight");
  link.href = option.search_url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  action.append(link, element("span", "checked", `Quoted ${formatChecked(option.checked_at)}`));

  row.append(destination, flight, price, comparison, action);
  return row;
}

function matchesFilter(option) {
  if (state.filter === "bucket") return option.on_bucket_list;
  if (state.filter === "below") return option.percent_below_median > 0;
  if (state.filter === "direct") return option.stops === 0;
  return true;
}

function makeListHeader() {
  const header = element("div", "list-header");
  ["Destination", "Outbound example", "Return fare", "vs median", ""].forEach((label) => {
    header.append(element("span", "", label));
  });
  return header;
}

function renderWeekends() {
  const container = document.querySelector("#weekends");
  container.replaceChildren();
  let visibleSections = 0;

  state.payload.weekends.forEach((weekend, index) => {
    const matches = weekend.options.filter(matchesFilter);
    if (!matches.length && state.filter !== "all") return;
    const initialLimit = state.payload.summary.initial_options_per_weekend;
    const expanded = state.view === "all"
      ? !state.collapsedWeekends.has(weekend.label)
      : state.expandedWeekends.has(weekend.label);
    const visible = expanded ? matches : matches.slice(0, initialLimit);

    visibleSections += 1;
    const section = element("section", "weekend-section");
    section.id = `weekend-${index + 1}`;

    const heading = element("div", "weekend-heading");
    heading.append(
      element("h2", "", weekend.label),
      element(
        "span",
        "option-count",
        visible.length === matches.length
          ? `${matches.length} option${matches.length === 1 ? "" : "s"}`
          : `${visible.length} of ${matches.length} options`,
      ),
    );

    const list = element("div", "flight-list");
    if (matches.length) {
      list.append(makeListHeader());
      visible.forEach((option) => list.append(makeFareRow(option)));
      if (matches.length > initialLimit) {
        const footer = element("div", "list-footer");
        const toggle = element(
          "button",
          "expand-button",
          expanded ? "Show top 3" : `Show all ${matches.length} options`,
        );
        toggle.type = "button";
        toggle.addEventListener("click", () => {
          if (expanded) {
            if (state.view === "all") {
              state.collapsedWeekends.add(weekend.label);
            } else {
              state.expandedWeekends.delete(weekend.label);
            }
          } else {
            if (state.view === "all") {
              state.collapsedWeekends.delete(weekend.label);
            } else {
              state.expandedWeekends.add(weekend.label);
            }
          }
          renderWeekends();
          if (expanded) {
            document.getElementById(`weekend-${index + 1}`)?.scrollIntoView({ block: "start" });
          }
        });
        footer.append(toggle);
        list.append(footer);
      }
    } else {
      list.append(
        element(
          "div",
          "empty-filter",
          `No realistic return fare under ${euro.format(state.payload.summary.max_return_price)} was found for this weekend.`,
        ),
      );
    }

    section.append(heading, list);
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

  if (summary.best_saving) {
    document.querySelector("#stat-saving").textContent = `${Math.round(summary.best_saving.percent * 100)}%`;
    document.querySelector("#stat-saving-place").textContent = `${summary.best_saving.destination} · ${summary.best_saving.weekend}`;
  } else {
    document.querySelector("#stat-saving").textContent = "—";
    document.querySelector("#stat-saving-place").textContent = "No eligible fares";
  }

  document.querySelector("#stat-updated").textContent = formatChecked(state.payload.generated_at);
  const live = document.querySelector("#live-status");
  live.className = "live-status ready";
  if (refresh.running) {
    live.querySelector("span:last-child").textContent = "Refreshing prices";
  } else if (refresh.last_error) {
    live.className = "live-status error";
    live.querySelector("span:last-child").textContent = "Showing saved data";
  } else {
    live.querySelector("span:last-child").textContent = "Hourly refresh active";
  }
}

function populateJump() {
  const select = document.querySelector("#weekend-select");
  select.replaceChildren(element("option", "", "All weekends"));
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
    state.expandedWeekends.clear();
    state.collapsedWeekends.clear();
    if (state.payload) renderWeekends();
  });
});

document.querySelectorAll(".view-button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".view-button").forEach((candidate) => candidate.classList.remove("active"));
    button.classList.add("active");
    state.view = button.dataset.view;
    state.expandedWeekends.clear();
    state.collapsedWeekends.clear();
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
