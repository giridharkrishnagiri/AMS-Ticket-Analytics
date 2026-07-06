import { useState } from "react";
import type { RefObject } from "react";

type TableExportActionsProps = {
  tableRef: RefObject<HTMLTableElement | null>;
  filename: string;
  label?: string;
  disabled?: boolean;
  className?: string;
};

function csvCell(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function copyTextToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "fixed";
  textArea.style.left = "-9999px";
  document.body.append(textArea);
  textArea.select();
  document.execCommand("copy");
  textArea.remove();
}

function tableRows(table: HTMLTableElement): string[][] {
  return Array.from(table.querySelectorAll("tr"))
    .map((row) =>
      Array.from(row.querySelectorAll("th,td")).map((cell) =>
        (cell.textContent ?? "").replace(/\s+/g, " ").trim()
      )
    )
    .filter((row) => row.length > 0);
}

export default function TableExportActions({
  tableRef,
  filename,
  label = "table",
  disabled = false,
  className = "",
}: TableExportActionsProps) {
  const [message, setMessage] = useState<string | null>(null);

  async function handleCopy() {
    const table = tableRef.current;
    if (!table) {
      setMessage("Table is not available yet.");
      return;
    }
    const rows = tableRows(table);
    try {
      await copyTextToClipboard(rows.map((row) => row.join("\t")).join("\n"));
      setMessage(`Copied ${label}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to copy table.");
    }
  }

  function handleDownload() {
    const table = tableRef.current;
    if (!table) {
      setMessage("Table is not available yet.");
      return;
    }
    const csv = tableRows(table)
      .map((row) => row.map(csvCell).join(","))
      .join("\r\n");
    downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), filename);
    setMessage("CSV downloaded.");
  }

  return (
    <>
      <div className={`validation-actions table-export-actions ${className}`.trim()}>
        <button
          className="secondary-button table-action-button"
          disabled={disabled}
          type="button"
          onClick={() => void handleCopy()}
        >
          Copy Table
        </button>
        <button
          className="secondary-button table-action-button"
          disabled={disabled}
          type="button"
          onClick={handleDownload}
        >
          Download CSV
        </button>
      </div>
      {message ? <p className="chart-copy-status">{message}</p> : null}
    </>
  );
}
