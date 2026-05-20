"use client";

import { jsPDF } from "jspdf";
import { useMemo, useRef } from "react";
import HoverGuide from "./HoverGuide";

type SchemaRow = {
  table_name?: string;
  column_name?: string;
  data_type?: string;
  relationship_info?: string;
};

type DiagramTable = {
  name: string;
  columns: Array<{ name: string; type: string }>;
};

type DiagramEdge = {
  from: string;
  to: string;
  label: string;
};

function normalizeName(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9_]/g, "");
}

function singular(value: string) {
  if (value.endsWith("ies")) return `${value.slice(0, -3)}y`;
  if (value.endsWith("ses")) return value.slice(0, -2);
  if (value.endsWith("s")) return value.slice(0, -1);
  return value;
}

function inferTargetTable(column: string, tableNames: string[]) {
  const normalized = normalizeName(column);
  if (!normalized.endsWith("_id")) return "";

  const base = normalized.slice(0, -3);
  const candidates = new Set([base, singular(base), `${base}s`, `${singular(base)}s`]);

  for (const table of tableNames) {
    const key = normalizeName(table);
    if (candidates.has(key) || candidates.has(singular(key))) {
      return table;
    }
  }
  return "";
}

function parseRelationshipHint(relationshipInfo: string, tableNames: string[]) {
  const lower = relationshipInfo.toLowerCase();
  for (const table of tableNames) {
    const key = table.toLowerCase();
    if (lower.includes(`${key}.`) || lower.includes(` ${key} `) || lower.endsWith(key)) {
      return table;
    }
  }
  return "";
}

function buildGraph(rows: SchemaRow[]) {
  const tableMap = new Map<string, DiagramTable>();

  for (const row of rows) {
    const table = String(row.table_name || "").trim();
    const column = String(row.column_name || "").trim();
    if (!table || !column) continue;

    if (!tableMap.has(table)) {
      tableMap.set(table, { name: table, columns: [] });
    }
    const entry = tableMap.get(table)!;
    const already = entry.columns.some((item) => item.name === column);
    if (!already) {
      entry.columns.push({ name: column, type: String(row.data_type || "-") });
    }
  }

  const tables = Array.from(tableMap.values()).sort((a, b) => a.name.localeCompare(b.name));
  const tableNames = tables.map((table) => table.name);
  const tableNameSet = new Set(tableNames);

  const edgeKeys = new Set<string>();
  const edges: DiagramEdge[] = [];

  for (const row of rows) {
    const from = String(row.table_name || "").trim();
    const column = String(row.column_name || "").trim();
    if (!from || !column || !tableNameSet.has(from)) continue;

    let to = "";
    const relationshipInfo = String(row.relationship_info || "").trim();
    if (relationshipInfo) {
      to = parseRelationshipHint(relationshipInfo, tableNames);
    }
    if (!to) {
      to = inferTargetTable(column, tableNames);
    }
    if (!to || to === from || !tableNameSet.has(to)) continue;

    const key = `${from}|${to}|${column}`;
    if (edgeKeys.has(key)) continue;
    edgeKeys.add(key);

    edges.push({ from, to, label: column });
  }

  return { tables, edges };
}

export default function SchemaERDiagram({ rows }: { rows: SchemaRow[] }) {
  const { tables, edges } = buildGraph(rows);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const fileBase = useMemo(() => {
    const first = tables[0]?.name || "schema";
    return `${first.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-er-diagram`;
  }, [tables]);

  if (!tables.length) {
    return <p className="text-sm text-slate-600">No schema metadata available to render ER diagram.</p>;
  }

  const entityWidth = 240;
  const entityHeight = 46;
  const xGap = 90;
  const yGap = 120;
  const attributeGap = 38;
  const maxAttributes = 6;
  const columnsPerRow = 3;

  const positions: Record<string, { x: number; y: number }> = {};
  tables.forEach((table, index) => {
    const row = Math.floor(index / columnsPerRow);
    const col = index % columnsPerRow;
    positions[table.name] = {
      x: 40 + col * (entityWidth + xGap),
      y: 40 + row * ((entityHeight + maxAttributes * attributeGap) + yGap),
    };
  });

  const rowsCount = Math.ceil(tables.length / columnsPerRow);
  const width = columnsPerRow * entityWidth + (columnsPerRow - 1) * xGap + 120;
  const height = Math.max(380, rowsCount * (entityHeight + maxAttributes * attributeGap) + (rowsCount - 1) * yGap + 120);

  function isPrimaryKey(tableName: string, columnName: string) {
    const normalized = normalizeName(columnName);
    const table = normalizeName(tableName);
    return normalized === "id" || normalized === `${table}_id`;
  }

  function isForeignKey(tableName: string, columnName: string, tableNames: string[]) {
    const normalized = normalizeName(columnName);
    if (!normalized.endsWith("_id")) return false;
    if (isPrimaryKey(tableName, columnName)) return false;
    return !!inferTargetTable(columnName, tableNames);
  }

  const tableNames = tables.map((table) => table.name);

  async function exportRaster(format: "png" | "jpeg") {
    if (!svgRef.current) return;

    const serializer = new XMLSerializer();
    const source = serializer.serializeToString(svgRef.current);
    const svgBlob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(svgBlob);

    try {
      const img = new Image();
      img.src = url;

      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve();
        img.onerror = () => reject(new Error("Failed to render schema image"));
      });

      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Canvas context unavailable");

      // Solid white background keeps exports clean and printable.
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(img, 0, 0);

      const mime = format === "png" ? "image/png" : "image/jpeg";
      const dataUrl = canvas.toDataURL(mime, 0.95);
      const link = document.createElement("a");
      link.href = dataUrl;
      link.download = `${fileBase}.${format === "png" ? "png" : "jpg"}`;
      link.click();
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  async function exportPdf() {
    if (!svgRef.current) return;

    const serializer = new XMLSerializer();
    const source = serializer.serializeToString(svgRef.current);
    const svgBlob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(svgBlob);

    try {
      const img = new Image();
      img.src = url;

      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve();
        img.onerror = () => reject(new Error("Failed to render schema image"));
      });

      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Canvas context unavailable");

      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(img, 0, 0);

      const imageData = canvas.toDataURL("image/png", 1.0);
      const orientation = width > height ? "l" : "p";
      const pdf = new jsPDF({ orientation, unit: "px", format: [width, height] });
      pdf.addImage(imageData, "PNG", 0, 0, width, height);
      pdf.save(`${fileBase}.pdf`);
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-slate-500">DBMS-style ER view: entities are rectangles and attributes are ovals.</p>
        <div className="flex gap-2">
          <HoverGuide text="Export the current ER diagram as a crisp PNG image.">
            <button type="button" onClick={() => exportRaster("png")} className="rounded-md bg-slate-700 px-3 py-1.5 text-xs font-semibold text-white">Download PNG</button>
          </HoverGuide>
          <HoverGuide text="Export the current ER diagram as a compressed JPG image.">
            <button type="button" onClick={() => exportRaster("jpeg")} className="rounded-md bg-slate-700 px-3 py-1.5 text-xs font-semibold text-white">Download JPG</button>
          </HoverGuide>
          <HoverGuide text="Export the full ER diagram to a print-friendly PDF document.">
            <button type="button" onClick={exportPdf} className="rounded-md bg-slate-700 px-3 py-1.5 text-xs font-semibold text-white">Download PDF</button>
          </HoverGuide>
        </div>
      </div>
      <div className="overflow-auto rounded-xl border border-slate-200 bg-slate-50">
        <svg ref={svgRef} width={width} height={height} role="img" aria-label="Entity Relationship diagram">
          <defs>
            <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#4f46e5" />
            </marker>
          </defs>

          {edges.map((edge) => {
            const fromPos = positions[edge.from];
            const toPos = positions[edge.to];
            if (!fromPos || !toPos) return null;

            const x1 = fromPos.x + entityWidth / 2;
            const y1 = fromPos.y + entityHeight / 2;
            const x2 = toPos.x + entityWidth / 2;
            const y2 = toPos.y + entityHeight / 2;
            const cx = (x1 + x2) / 2;
            const cy = (y1 + y2) / 2 - 12;

            return (
              <g key={`${edge.from}-${edge.to}-${edge.label}`}>
                <path
                  d={`M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`}
                  stroke="#4f46e5"
                  strokeWidth="1.8"
                  fill="none"
                  markerEnd="url(#arrowhead)"
                  opacity="0.9"
                />
                <text x={cx} y={cy} textAnchor="middle" fontSize="11" fill="#4338ca">
                  {edge.label}
                </text>
              </g>
            );
          })}

          {tables.map((table) => {
            const pos = positions[table.name];
            if (!pos) return null;
            const previewColumns = table.columns.slice(0, maxAttributes);
            const hasMore = table.columns.length > maxAttributes;

            return (
              <g key={table.name}>
                <rect x={pos.x} y={pos.y} width={entityWidth} height={entityHeight} rx={4} fill="#e0e7ff" stroke="#6366f1" strokeWidth={1.5} />
                <text x={pos.x + entityWidth / 2} y={pos.y + 29} textAnchor="middle" fontSize="13" fontWeight="700" fill="#312e81">
                  {table.name}
                </text>

                {previewColumns.map((column, index) => {
                  const y = pos.y + entityHeight + 24 + index * attributeGap;
                  const columnLabel = `${column.name}${column.type ? ` : ${column.type}` : ""}`;
                  const pk = isPrimaryKey(table.name, column.name);
                  const fk = isForeignKey(table.name, column.name, tableNames);
                  const fill = "#ffffff";
                  const stroke = "#94a3b8";

                  return (
                    <g key={`${table.name}-${column.name}`}>
                      <line x1={pos.x + entityWidth / 2} y1={pos.y + entityHeight} x2={pos.x + entityWidth / 2} y2={y - 14} stroke="#94a3b8" strokeWidth={1} />
                      <ellipse cx={pos.x + entityWidth / 2} cy={y} rx={104} ry={16} fill={fill} stroke={stroke} />
                      <text x={pos.x + entityWidth / 2} y={y + 4} textAnchor="middle" fontSize="10.5" fill="#0f172a">
                        {pk ? `[PK] ${columnLabel.length > 28 ? `${columnLabel.slice(0, 27)}...` : columnLabel}` : fk ? `[FK] ${columnLabel.length > 28 ? `${columnLabel.slice(0, 27)}...` : columnLabel}` : columnLabel.length > 34 ? `${columnLabel.slice(0, 33)}...` : columnLabel}
                      </text>
                    </g>
                  );
                })}

                {hasMore && (
                  <g>
                    <line
                      x1={pos.x + entityWidth / 2}
                      y1={pos.y + entityHeight}
                      x2={pos.x + entityWidth / 2}
                      y2={pos.y + entityHeight + 24 + previewColumns.length * attributeGap - 14}
                      stroke="#94a3b8"
                      strokeWidth={1}
                    />
                    <ellipse cx={pos.x + entityWidth / 2} cy={pos.y + entityHeight + 24 + previewColumns.length * attributeGap} rx={48} ry={14} fill="#f1f5f9" stroke="#94a3b8" />
                    <text x={pos.x + entityWidth / 2} y={pos.y + entityHeight + 24 + previewColumns.length * attributeGap + 4} textAnchor="middle" fontSize="10" fill="#475569">
                      more attributes...
                    </text>
                  </g>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
