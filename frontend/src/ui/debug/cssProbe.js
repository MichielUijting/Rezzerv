export function isUiDebugEnabled() {
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get("uiDebug") === "1") return true;
    if (localStorage.getItem("rezzerv_ui_debug") === "1") return true;
  } catch (e) {}
  return false;
}

function safeCssRules(sheet) {
  try {
    return sheet.cssRules || [];
  } catch (e) {
    return [];
  }
}

export function getComputedSnapshot(el) {
  const cs = window.getComputedStyle(el);
  return {
    tag: el.tagName.toLowerCase(),
    className: el.className || "",
    height: cs.height,
    minHeight: cs.minHeight,
    paddingTop: cs.paddingTop,
    paddingBottom: cs.paddingBottom,
    lineHeight: cs.lineHeight,
    borderSpacing: cs.borderSpacing,
    borderCollapse: cs.borderCollapse,
    boxSizing: cs.boxSizing,
    fontSize: cs.fontSize,
    fontWeight: cs.fontWeight,
  };
}

/**
 * Try to find CSS rules that match element and mention any of the provided properties.
 * This helps identify which selector is likely overriding the intended styling.
 */
export function findMatchingRules(el, properties = ["height", "min-height", "padding", "line-height"]) {
  const matches = [];
  const sheets = Array.from(document.styleSheets || []);
  for (const sheet of sheets) {
    const href = sheet.href || "(inline)";
    const rules = safeCssRules(sheet);
    for (const rule of rules) {
      if (!rule.selectorText || !rule.style) continue;
      let isMatch = false;
      try {
        isMatch = el.matches(rule.selectorText);
      } catch (e) {
        continue;
      }
      if (!isMatch) continue;

      const styleText = rule.style.cssText || "";
      const hasProp = properties.some(p => styleText.toLowerCase().includes(p));
      if (!hasProp) continue;

      matches.push({
        href,
        selector: rule.selectorText,
        cssText: styleText,
      });
    }
  }
  return matches.slice(0, 30); // cap for readability
}

export function measureTable(tableEl) {
  const out = {
    table: getComputedSnapshot(tableEl),
    headerRow: null,
    filterRow: null,
    firstBodyRow: null,
    headerCheckbox: null,
    bodyCheckbox: null,
    headerRules: [],
    filterRules: [],
    bodyRules: [],
    checkboxRules: [],
  };

  const thead = tableEl.querySelector("thead");
  const tbody = tableEl.querySelector("tbody");

  const headerRow = thead?.querySelector("tr:nth-child(1)");
  const filterRow = thead?.querySelector("tr:nth-child(2)");
  const firstBodyRow = tbody?.querySelector("tr");

  if (headerRow) out.headerRow = getComputedSnapshot(headerRow);
  if (filterRow) out.filterRow = getComputedSnapshot(filterRow);
  if (firstBodyRow) out.firstBodyRow = getComputedSnapshot(firstBodyRow);

  const headerCb = thead?.querySelector('input[type="checkbox"]');
  const bodyCb = tbody?.querySelector('input[type="checkbox"]');

  if (headerCb) out.headerCheckbox = getComputedSnapshot(headerCb);
  if (bodyCb) out.bodyCheckbox = getComputedSnapshot(bodyCb);

  if (headerRow) out.headerRules = findMatchingRules(headerRow, ["height", "min-height", "padding", "line-height"]);
  if (filterRow) out.filterRules = findMatchingRules(filterRow, ["height", "min-height", "padding", "line-height"]);
  if (firstBodyRow) out.bodyRules = findMatchingRules(firstBodyRow, ["height", "min-height", "padding", "line-height"]);
  if (headerCb) out.checkboxRules = findMatchingRules(headerCb, ["width", "height", "transform", "zoom", "accent-color"]);

  return out;
}