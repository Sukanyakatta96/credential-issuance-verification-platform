import { h, svg } from "./dom.js";

const PALETTE = ["#2f6fed", "#12a594", "#f2a31b", "#e5484d", "#8e4ec6", "#5b6b7f", "#30a46c", "#d6409f"];

function empty() { return h("p", { class: "muted" }, "No data yet."); }

export function barChart(rows, { labelKey = "label", valueKey = "count", height = 220 } = {}) {
  if (!rows.length) return empty();
  const width = 520, pad = { top: 16, right: 12, bottom: 56, left: 44 };
  const max = Math.max(...rows.map((r) => r[valueKey]), 1);
  const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
  const step = plotW / rows.length;
  const bars = rows.map((row, i) => {
    const barH = (row[valueKey] / max) * plotH;
    const x = pad.left + i * step + step * 0.15;
    const label = String(row[labelKey]);
    return svg("g", {},
      svg("rect", { x, y: pad.top + plotH - barH, width: step * 0.7, height: barH, fill: PALETTE[i % PALETTE.length], rx: 3 },
        svg("title", {}, `${label}: ${row[valueKey]}`)),
      svg("text", { x: x + step * 0.35, y: pad.top + plotH - barH - 4, "text-anchor": "middle", class: "chart-value" }, row[valueKey]),
      svg("text", { x: x + step * 0.35, y: height - pad.bottom + 14, "text-anchor": "end", class: "chart-label",
        transform: `rotate(-30 ${x + step * 0.35} ${height - pad.bottom + 14})` }, label.length > 22 ? label.slice(0, 21) + "…" : label));
  });
  return svg("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart", role: "img" },
    svg("line", { x1: pad.left, y1: pad.top + plotH, x2: width - pad.right, y2: pad.top + plotH, class: "chart-axis" }), bars);
}

export function lineChart(rows, { labelKey = "month", valueKey = "count", height = 220 } = {}) {
  if (!rows.length) return empty();
  const width = 520, pad = { top: 16, right: 16, bottom: 32, left: 44 };
  const max = Math.max(...rows.map((r) => r[valueKey]), 1);
  const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
  const x = (i) => pad.left + (rows.length === 1 ? plotW / 2 : (i / (rows.length - 1)) * plotW);
  const y = (v) => pad.top + plotH - (v / max) * plotH;
  const points = rows.map((r, i) => `${x(i)},${y(r[valueKey])}`).join(" ");
  return svg("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart", role: "img" },
    svg("line", { x1: pad.left, y1: pad.top + plotH, x2: width - pad.right, y2: pad.top + plotH, class: "chart-axis" }),
    svg("text", { x: pad.left - 6, y: pad.top + 4, "text-anchor": "end", class: "chart-label" }, max),
    svg("polyline", { points, fill: "none", stroke: PALETTE[0], "stroke-width": 2.5 }),
    rows.map((r, i) => svg("g", {},
      svg("circle", { cx: x(i), cy: y(r[valueKey]), r: 3.5, fill: PALETTE[0] }, svg("title", {}, `${r[labelKey]}: ${r[valueKey]}`)),
      svg("text", { x: x(i), y: height - 10, "text-anchor": "middle", class: "chart-label" }, String(r[labelKey]).slice(2)))));
}

export function donutChart(rows, { labelKey = "label", valueKey = "count" } = {}) {
  const total = rows.reduce((sum, r) => sum + r[valueKey], 0);
  if (!total) return empty();
  const radius = 70, circumference = 2 * Math.PI * radius;
  let offset = 0;
  const arcs = rows.map((row, i) => {
    const length = (row[valueKey] / total) * circumference;
    const arc = svg("circle", { cx: 100, cy: 100, r: radius, fill: "none", stroke: PALETTE[i % PALETTE.length], "stroke-width": 30,
      "stroke-dasharray": `${length} ${circumference - length}`, "stroke-dashoffset": -offset, transform: "rotate(-90 100 100)" },
      svg("title", {}, `${row[labelKey]}: ${row[valueKey]}`));
    offset += length;
    return arc;
  });
  const legend = h("ul", { class: "legend" }, rows.map((row, i) => h("li", {},
    h("span", { class: `swatch swatch-${i % PALETTE.length}` }), `${String(row[labelKey]).replace(/_/g, " ")} `,
    h("strong", {}, row[valueKey].toLocaleString()), ` (${((row[valueKey] / total) * 100).toFixed(1)}%)`)));
  return h("div", { class: "donut" },
    svg("svg", { viewBox: "0 0 200 200", class: "chart donut-svg", role: "img" }, arcs,
      svg("text", { x: 100, y: 105, "text-anchor": "middle", class: "donut-total" }, total.toLocaleString())), legend);
}
