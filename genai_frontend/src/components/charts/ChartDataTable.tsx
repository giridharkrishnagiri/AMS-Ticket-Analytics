import type { ChartTable } from "../../types/charts";

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

export function ChartDataTable({ table }: { table: ChartTable }) {
  if (table.columns.length === 0 || table.rows.length === 0) {
    return <p className="muted-inline">No chart data rows were returned.</p>;
  }

  return (
    <div className="table-scroll chart-data-table">
      <table>
        <thead>
          <tr>
            {table.columns.map((column) => (
              <th key={column.key}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, rowIndex) => (
            <tr key={`chart-row-${rowIndex}`}>
              {table.columns.map((column) => (
                <td key={column.key}>{formatCellValue(row[column.key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
