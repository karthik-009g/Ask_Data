import { useMemo } from "react";

type WorkflowStep = {
  id: string;
  title: string;
  description: string;
  chips: string[];
  accent: "prompt" | "model" | "route" | "source" | "sql" | "guard" | "result";
};

type VisualWorkflowProps = {
  prompt: string;
  selectedConnectionIds: number[];
  generatedQueries: any[];
  generationInfo: any;
  agenticTrace: any;
  executionTime: number;
  rowCount: number;
  errorMessage?: string;
};

const STOP_WORDS = new Set([
  "a",
  "an",
  "and",
  "are",
  "as",
  "at",
  "be",
  "by",
  "for",
  "from",
  "get",
  "give",
  "how",
  "in",
  "is",
  "me",
  "of",
  "on",
  "or",
  "show",
  "that",
  "the",
  "to",
  "top",
  "what",
  "which",
  "with",
]);

function normalizeArray(value: unknown): any[] {
  return Array.isArray(value) ? value : [];
}

function trimText(value: unknown): string {
  return String(value || "").trim();
}

function compactText(value: string): string {
  return trimText(value).replace(/\s+/g, " ");
}

function truncate(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, Math.max(0, maxLength - 3))}...`;
}

function extractSelectColumns(sqlText: string): string[] {
  const sql = compactText(sqlText);
  const match = sql.match(/select\s+(.+?)\s+from\s+/i);
  if (!match?.[1]) return [];

  const rawParts = match[1]
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 6);

  return rawParts.map((part) => {
    const withoutAlias = part.split(/\s+as\s+/i)[0] || part;
    const afterDot = withoutAlias.split(".").pop() || withoutAlias;
    return afterDot.replace(/[^a-zA-Z0-9_]/g, "").toLowerCase();
  }).filter(Boolean);
}

function extractPromptTerms(prompt: string): string[] {
  return Array.from(
    new Set(
      compactText(prompt)
        .toLowerCase()
        .split(/[^a-z0-9_]+/)
        .filter((term) => term.length >= 3 && !STOP_WORDS.has(term))
        .slice(0, 8)
    )
  );
}

function extractPlannerTable(step: any): string {
  const matchedTables = normalizeArray(step?.planner?.matched_tables);
  const bestMatch = trimText(matchedTables?.[0]?.table_name);
  if (bestMatch) return bestMatch;

  const insightTables = normalizeArray(step?.insight?.tables_used);
  const firstInsightTable = trimText(insightTables?.[0]);
  if (firstInsightTable) return firstInsightTable;

  return "";
}

export default function VisualWorkflow({
  prompt,
  selectedConnectionIds,
  generatedQueries,
  generationInfo,
  agenticTrace,
  executionTime,
  rowCount,
  errorMessage,
}: VisualWorkflowProps) {
  const workflowSteps = useMemo(() => {
    const steps: WorkflowStep[] = [];
    const promptText = compactText(prompt) || "No prompt captured for this run.";
    const generationMode = trimText(generationInfo?.mode || agenticTrace?.mode || "unknown");
    const provider = trimText(generationInfo?.provider || "system");
    const model = trimText(generationInfo?.model || "deterministic");
    const connections = normalizeArray(agenticTrace?.connections);
    const summary = agenticTrace?.summary || {};
    const generated = normalizeArray(generatedQueries);
    const firstQuery = trimText(generated?.[0]?.query_text);
    const firstLanguage = trimText(generated?.[0]?.query_language || "sql").toUpperCase();
    const usedTables = normalizeArray(agenticTrace?.tables_used).map((item) => trimText(item)).filter(Boolean);
    const scopeTables = normalizeArray(agenticTrace?.tables_in_scope).map((item) => trimText(item)).filter(Boolean);
    const rowCap = connections?.[0]?.policy?.max_rows ?? "-";

    const repairAttempts = connections.reduce((total: number, step: any) => {
      const attempts = normalizeArray(step?.repair?.attempts);
      return total + attempts.length;
    }, 0);

    const maxRepairAttempts = connections.reduce((maxAttempts: number, step: any) => {
      const next = Number(step?.repair?.max_attempts || 0);
      return Math.max(maxAttempts, next);
    }, 0);

    const sourceSelectionNote = selectedConnectionIds.length
      ? `Using ${selectedConnectionIds.length} user-selected source(s).`
      : `No source pre-selected. Planner auto-routed across ${Number(summary?.selected_connections || connections.length || 0)} source(s).`;

    const sqlColumns = extractSelectColumns(firstQuery);
    const promptTerms = extractPromptTerms(promptText);
    const focusTerms = promptTerms.filter(
      (term) =>
        sqlColumns.some((column) => column.includes(term)) ||
        usedTables.some((table) => table.toLowerCase().includes(term)) ||
        firstQuery.toLowerCase().includes(term)
    );

    steps.push({
      id: "prompt",
      title: "Prompt Input",
      description: truncate(promptText, 170),
      chips: ["Intent routed to analytics", `Terms: ${promptTerms.slice(0, 4).join(", ") || "n/a"}`],
      accent: "prompt",
    });

    steps.push({
      id: "model",
      title: "Model and SQL Engine",
      description: `${generationMode.toUpperCase()} generation via ${provider}/${model}.`,
      chips: [`Language: ${firstLanguage}`, `Queries generated: ${generated.length}`],
      accent: "model",
    });

    steps.push({
      id: "route",
      title: "Source Routing",
      description: sourceSelectionNote,
      chips: [
        `SQL sources: ${Number(summary?.sql_connections || 0)}`,
        `Mongo sources: ${Number(summary?.mongodb_connections || 0)}`,
      ],
      accent: "route",
    });

    connections.forEach((step: any, index: number) => {
      const planner = step?.planner || {};
      const connectionId = planner?.connection_id ?? index + 1;
      const connectionName = trimText(planner?.connection_name || `Connection ${index + 1}`);
      const dbType = trimText(planner?.db_type || generated?.[index]?.db_type || "unknown").toUpperCase();
      const confidence = trimText(planner?.confidence || "low");
      const bestTable = extractPlannerTable(step);
      const plannerMessage = trimText(planner?.clarification_question) || (bestTable
        ? `Planner prioritized ${bestTable} before execution.`
        : "Planner selected this source for guarded execution.");

      steps.push({
        id: `source-${index}`,
        title: `Source #${connectionId}: ${connectionName}`,
        description: truncate(plannerMessage, 140),
        chips: [
          `DB: ${dbType}`,
          `Confidence: ${confidence}`,
          bestTable ? `Table focus: ${bestTable}` : "Table focus: inferred",
        ],
        accent: "source",
      });
    });

    steps.push({
      id: "sql",
      title: "SQL Build",
      description: firstQuery
        ? truncate(compactText(firstQuery), 180)
        : "No SQL text available yet. Run a successful analytics query to visualize this step.",
      chips: [
        `Columns: ${sqlColumns.slice(0, 4).join(", ") || "n/a"}`,
        `Tables in scope: ${(scopeTables.length ? scopeTables : usedTables).slice(0, 3).join(", ") || "n/a"}`,
      ],
      accent: "sql",
    });

    steps.push({
      id: "guard",
      title: "Policy and Repair",
      description: `Read-only policy enforced${rowCap !== "-" ? `, row cap ${rowCap}` : ""}.`,
      chips: [
        `Repair attempts: ${repairAttempts}`,
        `Max configured: ${maxRepairAttempts || 0}`,
      ],
      accent: "guard",
    });

    steps.push({
      id: "result",
      title: "Execution Output",
      description: errorMessage
        ? `Execution ended with issue: ${truncate(compactText(errorMessage), 140)}`
        : `Returned ${rowCount} row(s) in ${(Number(executionTime) || 0).toFixed(3)}s.`,
      chips: [
        `Used tables: ${usedTables.slice(0, 3).join(", ") || "n/a"}`,
        `Focus: ${focusTerms.slice(0, 3).join(", ") || promptTerms.slice(0, 2).join(", ") || "n/a"}`,
      ],
      accent: "result",
    });

    return steps;
  }, [
    agenticTrace,
    errorMessage,
    executionTime,
    generatedQueries,
    generationInfo,
    prompt,
    rowCount,
    selectedConnectionIds,
  ]);

  const hasExecutionData = Boolean(agenticTrace) || generatedQueries.length > 0;

  return (
    <section className="visual-workflow-shell" aria-live="polite">
      <div className="visual-workflow-head">
        <h3 className="visual-workflow-title">Visual Workflow</h3>
        <p className="visual-workflow-subtitle">
          Dynamic path from prompt to planner routing, SQL generation, guardrails, and final result.
        </p>
      </div>

      {!hasExecutionData && (
        <p className="visual-workflow-empty">
          Run an analytics query to render a full execution graph. The workflow will auto-map the chosen source,
          table focus, model usage, and SQL flow in order.
        </p>
      )}

      <div className="visual-workflow-lane">
        <ol className="visual-workflow-track">
          {workflowSteps.map((step, index) => (
            <li key={step.id} className="visual-workflow-step">
              <article className={`visual-workflow-card accent-${step.accent}`}>
                <div className="visual-workflow-step-index">{index + 1}</div>
                <h4 className="visual-workflow-step-title">{step.title}</h4>
                <p className="visual-workflow-step-description">{step.description}</p>
                <div className="visual-workflow-chip-row">
                  {step.chips.filter(Boolean).map((chip) => (
                    <span key={chip} className="visual-workflow-chip">{chip}</span>
                  ))}
                </div>
              </article>
              {index < workflowSteps.length - 1 && <span className="visual-workflow-connector" aria-hidden="true" />}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}