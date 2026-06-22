import { useMemo, useState } from "react";

export type ExcelFilterOption = {
  value: string;
  label: string;
  count: number;
};

type ExcelMultiSelectFilterProps = {
  label: string;
  options: ExcelFilterOption[];
  selectedValues: string[];
  onChange: (values: string[]) => void;
};

function ExcelMultiSelectFilter({
  label,
  options,
  selectedValues,
  onChange,
}: ExcelMultiSelectFilterProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchText, setSearchText] = useState("");

  const visibleOptions = useMemo(() => {
    const query = searchText.trim().toLowerCase();
    if (!query) {
      return options;
    }
    return options.filter((option) => option.label.toLowerCase().includes(query));
  }, [options, searchText]);

  const selectedSet = useMemo(() => new Set(selectedValues), [selectedValues]);
  const allVisibleSelected =
    visibleOptions.length > 0 && visibleOptions.every((option) => selectedSet.has(option.value));

  function toggleValue(value: string) {
    if (selectedSet.has(value)) {
      onChange(selectedValues.filter((selectedValue) => selectedValue !== value));
      return;
    }
    onChange([...selectedValues, value]);
  }

  function toggleVisibleValues() {
    if (allVisibleSelected) {
      const visibleSet = new Set(visibleOptions.map((option) => option.value));
      onChange(selectedValues.filter((value) => !visibleSet.has(value)));
      return;
    }

    const nextValues = new Set(selectedValues);
    for (const option of visibleOptions) {
      nextValues.add(option.value);
    }
    onChange(Array.from(nextValues));
  }

  return (
    <div className="excel-filter">
      <button
        className={isOpen ? "excel-filter-trigger active" : "excel-filter-trigger"}
        type="button"
        onClick={() => setIsOpen((current) => !current)}
      >
        <span>{label}</span>
        <strong>{selectedValues.length === 0 ? "All" : `${selectedValues.length} selected`}</strong>
      </button>

      {isOpen ? (
        <div className="excel-filter-menu">
          <input
            aria-label={`Search ${label}`}
            placeholder="Search"
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
          />
          <label className="excel-filter-select-all">
            <input
              type="checkbox"
              checked={allVisibleSelected}
              disabled={visibleOptions.length === 0}
              onChange={toggleVisibleValues}
            />
            <span>{allVisibleSelected ? "Deselect visible" : "Select visible"}</span>
          </label>
          <div className="excel-filter-options">
            {visibleOptions.length === 0 ? (
              <p className="muted-text">No matching values.</p>
            ) : (
              visibleOptions.map((option) => (
                <label key={option.value}>
                  <input
                    type="checkbox"
                    checked={selectedSet.has(option.value)}
                    onChange={() => toggleValue(option.value)}
                  />
                  <span>
                    {option.label} <small>({option.count.toLocaleString()})</small>
                  </span>
                </label>
              ))
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default ExcelMultiSelectFilter;
