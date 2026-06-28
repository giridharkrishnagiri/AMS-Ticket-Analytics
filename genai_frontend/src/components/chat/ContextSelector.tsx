import type { ChatContext, ChatDomain, ContextOption } from "../../types/chat";

const domainOptions: ChatDomain[] = [
  "General",
  "Applications",
  "Tickets",
  "SLA / OLA",
  "Problems / Changes",
  "Dashboard"
];

type ContextSelectorProps = {
  context: ChatContext;
  customers: ContextOption[];
  projects: ContextOption[];
  isLoading: boolean;
  error: string | null;
  onChange: (context: ChatContext) => void;
};

export function ContextSelector({
  context,
  customers,
  projects,
  isLoading,
  error,
  onChange
}: ContextSelectorProps) {
  return (
    <section className="context-selector" aria-labelledby="chat-context-heading">
      <div>
        <p className="eyebrow">Context</p>
        <h2 id="chat-context-heading">Chat Context</h2>
      </div>
      <div className="context-grid">
        <label>
          <span>Customer</span>
          <select
            value={context.customer_id ?? ""}
            onChange={(event) =>
              onChange({
                ...context,
                customer_id: event.target.value || null,
                project_id: null
              })
            }
          >
            <option value="">No customer selected</option>
            {customers.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Project</span>
          <select
            value={context.project_id ?? ""}
            onChange={(event) =>
              onChange({
                ...context,
                project_id: event.target.value || null
              })
            }
          >
            <option value="">No project selected</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Domain</span>
          <select
            value={context.domain}
            onChange={(event) =>
              onChange({
                ...context,
                domain: event.target.value as ChatDomain
              })
            }
          >
            {domainOptions.map((domain) => (
              <option key={domain} value={domain}>
                {domain}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="helper-text">
        Phase 1C chat does not query live dashboard data yet. Data-aware Q&amp;A will be added in
        Phase 1D/1E using governed analytics tools.
      </p>
      {isLoading ? <p className="loading-text">Loading context options...</p> : null}
      {error ? <div className="status-message status-error">{error}</div> : null}
    </section>
  );
}
