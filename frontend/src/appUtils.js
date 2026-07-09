export const MAX_FILES = 10;
export const ACTIVE_BATCH_STATUSES = new Set(["queued", "processing"]);

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

export async function request(path, options) {
  const response = await fetch(apiUrl(path), options);
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message = typeof body === "object" && body?.detail ? body.detail : response.statusText;
    throw new Error(Array.isArray(message) ? message.map((item) => item.msg).join(", ") : message);
  }

  return body;
}

export function filenameFromPath(path) {
  return String(path || "").split(/[\\/]/).filter(Boolean).pop() || "";
}

export function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

export function resultRows(result) {
  return (result?.keyword_groups || []).map((group, index) => ({
    id: `${group.representative_keyword || "keyword"}-${index}`,
    representative: cleanText(group.representative_keyword),
    grouped: groupedKeywords(group),
    context: cleanText(group.context_text),
    exact: cleanText(group.exact_text)
  }));
}

export function totalSize(files) {
  return files.reduce((sum, file) => sum + file.size, 0);
}

export function fileKey(file) {
  return `${file.name}-${file.size}-${file.lastModified}`;
}

export function finishedFile(file) {
  return ["success", "cached"].includes(file.status) && file.output_path;
}

export function formatPercent(value, options = {}) {
  const numeric = Number(value || 0);
  const percent = options.alreadyPercent ? numeric : numeric * 100;
  return `${percent.toFixed(2)}%`;
}

export function formatSeconds(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return `${Number(value).toFixed(2)}s`;
}

export function evaluationStats(report) {
  const summary = report?.summary || {};
  return {
    accuracy: report?.overall_accuracy_percent ?? report?.accuracy_percent ?? 0,
    processingTime: report?.processing_time_seconds,
    expected: summary.expected_items ?? report?.expected ?? 0,
    predicted: summary.predicted_items ?? report?.found ?? 0,
    matched: summary.matched_items ?? report?.matched ?? 0,
    missing: summary.missing_items ?? countItems(report?.missing_items),
    extra: summary.extra_items ?? countItems(report?.extra_items),
    precision: report?.precision ?? 0,
    recall: report?.recall ?? 0,
    f1: report?.f1 ?? 0,
    textMatchRate: report?.text_match_rate ?? 0
  };
}

export function evaluationItemLabel(item) {
  if (typeof item === "string") {
    return item;
  }
  return cleanText(
    item?.representative_keyword ||
      item?.normalized_key ||
      item?.id ||
      "Untitled item"
  );
}

export function evaluationItems(report, key, fallbackKey) {
  const values = report?.[key] || report?.[fallbackKey] || [];
  return Array.isArray(values) ? values.slice(0, 8) : [];
}

function groupedKeywords(group) {
  const seen = new Set();
  const values = [group.representative_keyword, ...(group.related_keywords || [])];

  return values
    .map(cleanText)
    .filter((value) => {
      const key = value.toLowerCase();
      if (!value || seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    })
    .join(", ");
}

function countItems(value) {
  return Array.isArray(value) ? value.length : 0;
}
