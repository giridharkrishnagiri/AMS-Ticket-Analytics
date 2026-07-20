import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import "./styles.css";
import "./mvp18Simplified.css";

import {
  clearStoredSession,
  analyzeWorkshop,
  createDeliverable,
  createEngagement,
  createSubtask,
  createTask,
  createWorkshop,
  createWorkshopAction,
  createWorkstream,
  deleteDeliverable,
  deleteEngagement,
  deleteSubtask,
  deleteTask,
  deleteWorkshop,
  deleteWorkshopAction,
  deleteWorkstream,
  getDashboardStatusSummary,
  getDeliverableWorkspace,
  getAllDeliverables,
  getAllSubtasks,
  getAllTasks,
  getAllWorkstreams,
  getEngagements,
  getEngagementWorkspace,
  getLlmPrompts,
  getMyWork,
  getMyWorkDeliverableWorkspace,
  getMyWorkSubtaskWorkspace,
  getMyWorkTaskWorkspace,
  getMyWorkWorkstreamWorkspace,
  getReminderIndicator,
  getStoredSession,
  getSubtaskWorkspace,
  getTaskWorkspace,
  getWorkshop,
  getWorkshopPromptPreview,
  getWorkshops,
  getWorkstreamWorkspace,
  login,
  storeSession,
  updateDeliverable,
  updateEngagement,
  updateLlmPrompt,
  updateSubtask,
  updateTask,
  updateWorkshop,
  updateWorkshopAction,
  updateWorkshopAnalysis,
  updateWorkstream,
  type DashboardStatusSummary,
  type DeliverableWorkspace,
  type EngagementWorkspace,
  type EntitySummary,
  type HierarchyFormPayload,
  type LlmPromptTemplate,
  type MyWorkResponse,
  type PromptPreview,
  type ReminderIndicator,
  type StatusBucket,
  type StoredSession,
  type SubtaskWorkspace,
  type TaskWorkspace,
  type Workshop,
  type WorkshopAction,
  type WorkshopFormPayload,
  type WorkshopListItem,
  type WorkstreamWorkspace,
} from "./mvp18UiApi";
import { Mvp18WorkspacePanel } from "./Mvp18WorkspacePanel";

type RouteState = {
  path: string;
  parts: string[];
};

type BreadcrumbViewItem = {
  label: string;
  path?: string;
};

type BreadcrumbWorkspaceData = EngagementWorkspace | WorkstreamWorkspace | DeliverableWorkspace | TaskWorkspace | SubtaskWorkspace | Workshop | null;

type BreadcrumbQueryConfig = {
  queryKey: unknown[];
  queryFn: () => Promise<BreadcrumbWorkspaceData>;
};

type EntityKind = "engagement" | "workstream" | "deliverable" | "task" | "subtask";

type FormMode = "create" | "edit";

type MyWorkListEntityKind = Extract<EntityKind, "workstream" | "deliverable" | "task">;

type MyWorkListKey =
  | "primary_workstreams"
  | "secondary_workstreams"
  | "primary_deliverables"
  | "secondary_deliverables"
  | "primary_tasks"
  | "secondary_tasks";

type MyWorkListConfig = {
  key: MyWorkListKey;
  label: string;
  helper: string;
  sectionTitle: string;
  entityKind: MyWorkListEntityKind;
  emptyLabel: string;
};

type FormState = {
  mode: FormMode;
  entityKind: EntityKind;
  parentId?: string;
  item?: EntitySummary;
};

type WorkshopFormState = {
  mode: FormMode;
  item?: Workshop;
};

const STATUS_OPTIONS = [
  "Not Started",
  "In Progress",
  "On Hold - Waiting for Information",
  "On Hold - Dependency",
  "Submitted for Review",
  "Rework Required",
  "Completed",
  "Cancelled",
];

const DEFAULT_MY_WORK_OWNER = "Giridhar";

const MY_WORK_LIST_CONFIGS: MyWorkListConfig[] = [
  {
    key: "primary_workstreams",
    label: "Primary Workstreams",
    helper: "You are primary owner",
    sectionTitle: "Primary Workstreams",
    entityKind: "workstream",
    emptyLabel: "No primary workstreams found.",
  },
  {
    key: "secondary_workstreams",
    label: "Secondary Workstreams",
    helper: "You are support/secondary",
    sectionTitle: "Secondary Workstreams",
    entityKind: "workstream",
    emptyLabel: "No secondary workstreams found.",
  },
  {
    key: "primary_deliverables",
    label: "Primary Deliverables",
    helper: "Direct deliverable list",
    sectionTitle: "Primary Deliverables",
    entityKind: "deliverable",
    emptyLabel: "No primary deliverables found.",
  },
  {
    key: "secondary_deliverables",
    label: "Secondary Deliverables",
    helper: "Direct deliverable list",
    sectionTitle: "Secondary Deliverables",
    entityKind: "deliverable",
    emptyLabel: "No secondary deliverables found.",
  },
  {
    key: "primary_tasks",
    label: "Primary Tasks",
    helper: "Direct task list",
    sectionTitle: "Primary Tasks",
    entityKind: "task",
    emptyLabel: "No primary tasks found.",
  },
  {
    key: "secondary_tasks",
    label: "Secondary Tasks",
    helper: "Direct task list",
    sectionTitle: "Secondary Tasks",
    entityKind: "task",
    emptyLabel: "No secondary tasks found.",
  },
];

const MY_WORK_ENTITY_LABELS: Record<MyWorkListEntityKind, { singular: string; plural: string }> = {
  workstream: { singular: "workstream", plural: "workstreams" },
  deliverable: { singular: "deliverable", plural: "deliverables" },
  task: { singular: "task", plural: "tasks" },
};

function getMyWorkOwnerName(): string {
  const session = getStoredSession();
  return session?.display_name?.trim() || session?.username?.trim() || DEFAULT_MY_WORK_OWNER;
}

function normalizePath(): RouteState {
  const path = window.location.pathname || "/";
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const parts = normalizedPath.split("/").filter(Boolean);
  return { path: normalizedPath, parts };
}

function navigateTo(path: string) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  if (window.location.pathname !== normalizedPath) {
    window.history.pushState({}, "", normalizedPath);
  }

  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function entityLabel(item: EntitySummary): string {
  return item.name || item.title || item.external_id || item.id;
}

function breadcrumbEntityLabel(item: EntitySummary | null | undefined, fallback: string): string {
  return item?.name?.trim() || item?.title?.trim() || item?.description?.trim() || fallback;
}

function shortId(id: string): string {
  return id.slice(0, 8);
}

function formatDate(value: string | null | undefined): string {
  return value || "-";
}


const TASK_METADATA_LABELS = [
  "Workstream",
  "Workstream ID",
  "Deliverable",
  "Deliverable ID",
  "Phase",
  "Internal checkpoint",
  "RAG",
  "Dependency/Input Needed",
  "Next Action",
  "Due Health",
  "Support",
];

type TaskMetadataItem = {
  label: string;
  value: string;
};

function extractTaskMetadata(description: string | null | undefined): TaskMetadataItem[] {
  if (!description) {
    return [];
  }

  const text = description.replace(/\s+/g, " ").trim();
  const matches = TASK_METADATA_LABELS
    .map((label) => {
      const index = text.toLowerCase().indexOf(`${label.toLowerCase()}:`);
      return index >= 0 ? { label, index } : null;
    })
    .filter((item): item is { label: string; index: number } => item !== null)
    .sort((left, right) => left.index - right.index);

  if (matches.length < 2) {
    return [];
  }

  return matches
    .map((match, index) => {
      const valueStart = match.index + match.label.length + 1;
      const valueEnd = index + 1 < matches.length ? matches[index + 1].index : text.length;
      return {
        label: match.label,
        value: text.slice(valueStart, valueEnd).trim(),
      };
    })
    .filter((item) => item.value.length > 0);
}

function TaskDescriptionDetails({ description }: { description: string | null | undefined }) {
  const metadata = extractTaskMetadata(description);

  if (metadata.length === 0) {
    return description ? <p>{description}</p> : null;
  }

  return (
    <div className="mvp18-task-metadata-grid">
      {metadata.map((item) => (
        <div className="mvp18-task-metadata-item" key={item.label}>
          <span className="mvp18-task-metadata-label">{item.label}</span>
          <span className="mvp18-task-metadata-value">{item.value}</span>
        </div>
      ))}
    </div>
  );
}

function statusClassText(bucket: StatusBucket): string {
  return `Not Started: ${bucket.not_started} | In Progress: ${bucket.in_progress} | On Hold: ${bucket.on_hold} | Completed: ${bucket.completed}`;
}

function StatusBadge({ status }: { status?: string | null }) {
  return <span className="mvp18-status-badge">{status || "No Status"}</span>;
}

function LoadingPanel({ label = "Loading..." }: { label?: string }) {
  return <div className="mvp18-panel">{label}</div>;
}

function ErrorPanel({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Unknown error";
  return <div className="mvp18-error">{message}</div>;
}

function EmptyPanel({ label }: { label: string }) {
  return <div className="mvp18-empty">{label}</div>;
}

function LoginPage({ onLogin }: { onLogin: (session: StoredSession) => void }) {
  const [username, setUsername] = useState("giridhar");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: (response) => {
      const session = storeSession(response);
      setMessage("");
      onLogin(session);
      window.location.replace("/");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "Login failed.");
    },
  });

  return (
    <div className="mvp18-login-page">
      <div className="mvp18-login-card">
        <h1>ASM Engagement Cockpit</h1>
        <p>Sign in to continue to the cockpit workspace.</p>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            loginMutation.mutate({ username, password });
          }}
        >
          <label>
            Username
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoFocus />
          </label>

          <label>
            Password
            <input value={password} type="password" onChange={(event) => setPassword(event.target.value)} />
          </label>

          <button className="mvp18-button-primary" type="submit" disabled={loginMutation.isPending}>
            {loginMutation.isPending ? "Signing in..." : "Login"}
          </button>

          {message ? <div className="mvp18-error">{message}</div> : null}
        </form>
      </div>
    </div>
  );
}

function ReminderButton({ indicator }: { indicator?: ReminderIndicator }) {
  const color = indicator?.color || "gray";
  const count = indicator?.total_active ?? 0;
  const label = indicator?.label || "No active reminders";

  return (
    <button
      className={`mvp18-reminder-button mvp18-reminder-${color}`}
      title={label}
      onClick={() => {
        alert(
          `Reminders\n\nTotal active: ${count}\nOverdue: ${indicator?.overdue ?? 0}\nDue within 2 days: ${indicator?.due_within_2_days ?? 0}\nOther active: ${indicator?.other_active ?? 0}`,
        );
      }}
    >
      🔔 {count}
    </button>
  );
}

function AppShell({
  children,
  session,
  setSession,
  breadcrumb,
}: {
  children: React.ReactNode;
  session: StoredSession | null;
  setSession: (session: StoredSession | null) => void;
  breadcrumb: BreadcrumbViewItem[];
}) {
  const reminderQuery = useQuery({
    queryKey: ["mvp18-reminder-indicator"],
    queryFn: getReminderIndicator,
    refetchInterval: 60000,
    retry: 1,
  });

  const currentPath = normalizePath().path;
  const navItems = [
    { label: "Dashboard", path: "/" },
    { label: "Engagements", path: "/engagements" },
    { label: "Workshops", path: "/workshops" },
    { label: "My Work", path: "/my-work" },
    { label: "Reminders", path: "/reminders" },
    { label: "Reports", path: "/reports" },
    { label: "Operations", path: "/operations" },
    { label: "Settings", path: "/settings" },
  ];

  return (
    <div className="mvp18-shell">
      <aside className="mvp18-sidebar">
        <div className="mvp18-brand">ASM Cockpit</div>
        <nav className="mvp18-nav">
          {navItems.map((item) => (
            <button
              key={item.path}
              className={currentPath === item.path ? "active" : ""}
              onClick={() => navigateTo(item.path)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="mvp18-main">
        <header className="mvp18-topbar">
          <div className="mvp18-breadcrumb">
            <button className="mvp18-breadcrumb-link mvp18-breadcrumb-root" onClick={() => navigateTo("/")}>
              ASM Engagement Cockpit
            </button>
            {breadcrumb.length === 0 ? (
              <span> / Dashboard</span>
            ) : (
              breadcrumb.map((item) => (
                <span key={`${item.label}-${item.path || "current"}`}>
                  <span> / </span>
                  {item.path ? (
                    <button className="mvp18-breadcrumb-link" title={item.label} onClick={() => navigateTo(item.path || "/")}>
                      {item.label}
                    </button>
                  ) : (
                    <span className="mvp18-breadcrumb-current" title={item.label}>{item.label}</span>
                  )}
                </span>
              ))
            )}
          </div>

          <div className="mvp18-top-actions">
            <ReminderButton indicator={reminderQuery.data} />
            <span>{session?.display_name || "Local User"}</span>
            <button
              className="mvp18-button-secondary"
              onClick={() => {
                clearStoredSession();
                setSession(null);
                window.location.replace("/login");
              }}
            >
              Logout
            </button>
          </div>
        </header>

        <div className="mvp18-content">{children}</div>
      </main>
    </div>
  );
}

function SummaryCard({ title, bucket, path }: { title: string; bucket: StatusBucket; path: string }) {
  return (
    <button className="mvp18-summary-card" onClick={() => navigateTo(path)}>
      <span>{title}</span>
      <strong>{bucket.total}</strong>
      <div className="mvp18-status-row">
        <div>{statusClassText(bucket)}</div>
        {bucket.other > 0 ? <div>Other: {bucket.other}</div> : null}
      </div>
    </button>
  );
}

function DashboardPage() {
  const summaryQuery = useQuery({
    queryKey: ["mvp18-dashboard-status-summary"],
    queryFn: getDashboardStatusSummary,
    retry: 1,
  });

  if (summaryQuery.isLoading) {
    return <LoadingPanel label="Loading dashboard summary..." />;
  }

  if (summaryQuery.isError) {
    return <ErrorPanel error={summaryQuery.error} />;
  }

  const summary = summaryQuery.data as DashboardStatusSummary;

  return (
    <>
      <div className="mvp18-page-header">
        <div>
          <h1>Dashboard</h1>
          <p>Clean executive view of engagement hierarchy and status counts.</p>
        </div>
      </div>

      <div className="mvp18-card-grid">
        <SummaryCard title="Engagements" bucket={summary.engagements} path="/engagements" />
        <SummaryCard title="Workstreams" bucket={summary.workstreams} path="/workstreams" />
        <SummaryCard title="Deliverables" bucket={summary.deliverables} path="/deliverables" />
        <SummaryCard title="Tasks" bucket={summary.tasks} path="/tasks" />
        <SummaryCard title="Sub-tasks" bucket={summary.subtasks} path="/subtasks" />
      </div>
    </>
  );
}

function EntityCard({
  item,
  viewLabel,
  onView,
  onEdit,
  onDelete,
  deleteLabel,
}: {
  item: EntitySummary;
  viewLabel: string;
  onView: () => void;
  onEdit: () => void;
  onDelete: () => void;
  deleteLabel: string;
}) {
  return (
    <div className="mvp18-entity-card">
      <div>
        <h3>{entityLabel(item)}</h3>
        <div className="mvp18-entity-meta">
          {item.external_id ? <span>ID: {item.external_id}</span> : <span>Record: {shortId(item.id)}</span>}
          <StatusBadge status={item.status} />
          <span>Primary: {item.owner_name || "-"}</span>
          {item.secondary_owner_name ? <span>Secondary: {item.secondary_owner_name}</span> : null}
          <span>Target: {formatDate(item.target_date)}</span>
          <span>Progress: {item.progress_percent ?? 0}%</span>
        </div>
        <TaskDescriptionDetails description={item.description} />
      </div>

      <div className="mvp18-actions">
        <button className="mvp18-button-primary" onClick={onView}>{viewLabel}</button>
        <button className="mvp18-button-secondary" onClick={onEdit}>Change</button>
        <button className="mvp18-button-danger" onClick={onDelete}>{deleteLabel}</button>
      </div>
    </div>
  );
}

function HierarchyFormModal({
  state,
  onClose,
  onSubmit,
}: {
  state: FormState;
  onClose: () => void;
  onSubmit: (payload: HierarchyFormPayload) => void;
}) {
  const isTitleBased = state.entityKind === "task" || state.entityKind === "subtask";
  const item = state.item;

  const [externalId, setExternalId] = useState(item?.external_id || "");
  const [label, setLabel] = useState(isTitleBased ? item?.title || "" : item?.name || "");
  const [description, setDescription] = useState(item?.description || "");
  const [status, setStatus] = useState(item?.status || "Not Started");
  const [priority, setPriority] = useState(item?.priority || "");
  const [ownerName, setOwnerName] = useState(item?.owner_name || "");
  const [startDate, setStartDate] = useState(item?.start_date || "");
  const [targetDate, setTargetDate] = useState(item?.target_date || "");

  const title = `${state.mode === "create" ? "Add" : "Change"} ${state.entityKind}`;

  return (
    <div className="mvp18-modal-backdrop">
      <div className="mvp18-modal">
        <h2>{title}</h2>

        <form
          className="mvp18-form"
          onSubmit={(event) => {
            event.preventDefault();
            const payload: HierarchyFormPayload = {
              external_id: externalId || null,
              description: description || null,
              status,
              priority: priority || null,
              owner_name: ownerName || null,
              start_date: startDate || null,
            };

            if (isTitleBased) {
              payload.title = label;
              payload.target_completion_date = targetDate || null;
            } else if (state.entityKind === "engagement") {
              payload.name = label;
              payload.target_end_date = targetDate || null;
            } else {
              payload.name = label;
              payload.target_completion_date = targetDate || null;
            }

            onSubmit(payload);
          }}
        >
          <div className="mvp18-form-grid">
            {state.entityKind !== "engagement" ? (
              <label>
                External ID
                <input value={externalId} onChange={(event) => setExternalId(event.target.value)} />
              </label>
            ) : null}

            <label>
              {isTitleBased ? "Title" : "Name"}
              <input value={label} onChange={(event) => setLabel(event.target.value)} required />
            </label>

            <label>
              Status
              <select value={status} onChange={(event) => setStatus(event.target.value)}>
                {STATUS_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>

            {(state.entityKind === "task" || state.entityKind === "subtask") ? (
              <label>
                Priority
                <input value={priority} onChange={(event) => setPriority(event.target.value)} />
              </label>
            ) : null}

            <label>
              Owner
              <input value={ownerName} onChange={(event) => setOwnerName(event.target.value)} />
            </label>

            <label>
              Start Date
              <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
            </label>

            <label>
              Target Date
              <input type="date" value={targetDate} onChange={(event) => setTargetDate(event.target.value)} />
            </label>
          </div>

          <label>
            Description
            <textarea value={description} rows={4} onChange={(event) => setDescription(event.target.value)} />
          </label>

          <div className="mvp18-actions">
            <button className="mvp18-button-secondary" type="button" onClick={onClose}>Cancel</button>
            <button className="mvp18-button-primary" type="submit">Save</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function GlobalEntityListPage({
  title,
  subtitle,
  queryKey,
  queryFn,
  pathPrefix,
  emptyLabel,
}: {
  title: string;
  subtitle: string;
  queryKey: string;
  queryFn: () => Promise<EntitySummary[]>;
  pathPrefix: string;
  emptyLabel: string;
}) {
  const query = useQuery({ queryKey: [queryKey], queryFn, retry: 1 });

  if (query.isLoading) return <LoadingPanel label={`Loading ${title.toLowerCase()}...`} />;
  if (query.isError) return <ErrorPanel error={query.error} />;

  const items = query.data ?? [];

  return (
    <>
      <div className="mvp18-page-header">
        <div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
      </div>

      <div className="mvp18-list">
        {items.length === 0 ? <EmptyPanel label={emptyLabel} /> : null}
        {items.map((item) => (
          <div className="mvp18-entity-card" key={item.id}>
            <div>
              <h3>{entityLabel(item)}</h3>
              <div className="mvp18-entity-meta">
                {item.external_id ? <span>ID: {item.external_id}</span> : <span>Record: {shortId(item.id)}</span>}
                <StatusBadge status={item.status} />
                <span>Owner: {item.owner_name || "-"}</span>
                <span>Target: {formatDate(item.target_date)}</span>
                <span>Progress: {item.progress_percent ?? 0}%</span>
              </div>
              <TaskDescriptionDetails description={item.description} />
            </div>

            <div className="mvp18-actions">
              <button className="mvp18-button-primary" onClick={() => navigateTo(`${pathPrefix}/${item.id}`)}>
                View
              </button>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function formatHours(value: string | number | null | undefined): string {
  if (value == null || value === "") return "-";
  return `${value} hr${Number(value) === 1 ? "" : "s"}`;
}

function WorkshopFormModal({
  state,
  onClose,
  onSubmit,
}: {
  state: WorkshopFormState;
  onClose: () => void;
  onSubmit: (payload: WorkshopFormPayload) => void;
}) {
  const item = state.item;
  const [workshopDate, setWorkshopDate] = useState(item?.workshop_date || new Date().toISOString().slice(0, 10));
  const [title, setTitle] = useState(item?.title || "");
  const [functionalTrack, setFunctionalTrack] = useState(item?.functional_track || "");
  const [participantsText, setParticipantsText] = useState(item?.participants_text || "");
  const [agenda, setAgenda] = useState(item?.agenda || "");
  const [durationHours, setDurationHours] = useState(item?.duration_hours == null ? "" : String(item.duration_hours));
  const [recordingPath, setRecordingPath] = useState(item?.recording_path || "");
  const [transcriptFile, setTranscriptFile] = useState<File | null>(null);

  return (
    <div className="mvp18-modal-backdrop" role="dialog" aria-modal="true">
      <div className="mvp18-modal">
        <h2>{state.mode === "create" ? "Create Workshop" : "Edit Workshop"}</h2>
        <form
          className="mvp18-form"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit({
              workshop_date: workshopDate,
              title,
              functional_track: functionalTrack,
              participants_text: participantsText,
              agenda,
              duration_hours: durationHours,
              recording_path: recordingPath,
              transcript_file: transcriptFile,
            });
          }}
        >
          <div className="mvp18-form-grid">
            <label>
              Workshop Date
              <input type="date" value={workshopDate} onChange={(event) => setWorkshopDate(event.target.value)} required />
            </label>

            <label>
              Duration
              <select value={durationHours} onChange={(event) => setDurationHours(event.target.value)}>
                <option value="">Not set</option>
                <option value="0.5">0.5 hours</option>
                <option value="1">1 hour</option>
                <option value="2">2 hours</option>
                <option value="2.5">2.5 hours</option>
              </select>
            </label>

            <label>
              Functional Track
              <input value={functionalTrack} onChange={(event) => setFunctionalTrack(event.target.value)} />
            </label>
          </div>

          <label>
            Workshop Title
            <input value={title} onChange={(event) => setTitle(event.target.value)} required />
          </label>

          <label>
            Participant List
            <textarea value={participantsText} rows={4} onChange={(event) => setParticipantsText(event.target.value)} />
          </label>

          <label>
            Agenda
            <textarea value={agenda} rows={4} onChange={(event) => setAgenda(event.target.value)} />
          </label>

          <label>
            Transcript Upload
            <input
              type="file"
              accept=".vtt,.docx,.txt,.srt"
              onChange={(event) => setTranscriptFile(event.target.files?.[0] || null)}
            />
          </label>

          {item?.transcript_filename ? <div className="mvp18-status-row">Current transcript: {item.transcript_filename}</div> : null}

          <label>
            Meeting Recording Path
            <input value={recordingPath} onChange={(event) => setRecordingPath(event.target.value)} placeholder="C:\\AIProjects\\..." />
          </label>

          <div className="mvp18-actions">
            <button className="mvp18-button-secondary" type="button" onClick={onClose}>Cancel</button>
            <button className="mvp18-button-primary" type="submit">Save</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function PromptPreviewModal({ preview, onClose }: { preview: PromptPreview; onClose: () => void }) {
  return (
    <div className="mvp18-modal-backdrop" role="dialog" aria-modal="true">
      <div className="mvp18-modal mvp18-wide-modal">
        <h2>LLM Prompts</h2>
        <div className="mvp18-form">
          <label>
            System Prompt
            <textarea value={preview.system_prompt} rows={8} readOnly />
          </label>
          <label>
            User Prompt
            <textarea value={preview.user_prompt} rows={14} readOnly />
          </label>
          <div className="mvp18-actions">
            <button className="mvp18-button-secondary" type="button" onClick={onClose}>Close</button>
            <button className="mvp18-button-primary" type="button" onClick={() => navigateTo("/settings")}>Edit Prompt Library</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function WorkshopsPage() {
  const queryClient = useQueryClient();
  const [formState, setFormState] = useState<WorkshopFormState | null>(null);
  const workshopsQuery = useQuery({ queryKey: ["workshops"], queryFn: getWorkshops, retry: 1 });

  const createMutation = useMutation({
    mutationFn: createWorkshop,
    onSuccess: () => {
      setFormState(null);
      queryClient.invalidateQueries({ queryKey: ["workshops"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: WorkshopFormPayload }) => updateWorkshop(id, payload),
    onSuccess: (item) => {
      setFormState(null);
      queryClient.invalidateQueries({ queryKey: ["workshops"] });
      queryClient.invalidateQueries({ queryKey: ["workshop", item.id] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteWorkshop,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workshops"] }),
  });

  if (workshopsQuery.isLoading) return <LoadingPanel label="Loading workshops..." />;
  if (workshopsQuery.isError) return <ErrorPanel error={workshopsQuery.error} />;

  const items = workshopsQuery.data ?? [];

  return (
    <>
      <div className="mvp18-page-header">
        <div>
          <h1>Workshops</h1>
          <p>Capture workshop context, transcripts, recordings, notes, and action items.</p>
        </div>
        <button className="mvp18-button-primary" onClick={() => setFormState({ mode: "create" })}>Create Workshop</button>
      </div>

      <div className="mvp18-list">
        {items.length === 0 ? <EmptyPanel label="No workshops yet." /> : null}
        {items.map((item: WorkshopListItem) => (
          <div className="mvp18-entity-card" key={item.id}>
            <div>
              <h3>{item.title}</h3>
              <div className="mvp18-entity-meta">
                <span>Date: {formatDate(item.workshop_date)}</span>
                <span>Track: {item.functional_track || "-"}</span>
                <span>Duration: {formatHours(item.duration_hours)}</span>
                <span>Actions: {item.action_count}</span>
                <span>Transcript: {item.transcript_filename ? "Uploaded" : "-"}</span>
              </div>
            </div>
            <div className="mvp18-actions">
              <button className="mvp18-button-primary" onClick={() => navigateTo(`/workshops/${item.id}`)}>View</button>
              <button
                className="mvp18-button-secondary"
                onClick={async () => {
                  const fullItem = await queryClient.fetchQuery({
                    queryKey: ["workshop", item.id],
                    queryFn: () => getWorkshop(item.id),
                  });
                  setFormState({ mode: "edit", item: fullItem });
                }}
              >
                Edit
              </button>
              <button
                className="mvp18-button-danger"
                onClick={() => {
                  const ok = window.confirm("Are you sure you want to delete this workshop?\n\nThis will delete its extracted notes and action items.");
                  if (ok) deleteMutation.mutate(item.id);
                }}
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {formState ? (
        <WorkshopFormModal
          state={formState}
          onClose={() => setFormState(null)}
          onSubmit={(payload) => {
            if (formState.mode === "create") {
              createMutation.mutate(payload);
            } else if (formState.item) {
              updateMutation.mutate({ id: formState.item.id, payload });
            }
          }}
        />
      ) : null}
    </>
  );
}

function WorkshopActionRow({ action, workshopId }: { action: WorkshopAction; workshopId: string }) {
  const queryClient = useQueryClient();
  const [actionText, setActionText] = useState(action.action_text);
  const [ownerName, setOwnerName] = useState(action.owner_name || "");
  const [dueDate, setDueDate] = useState(action.due_date || "");
  const [status, setStatus] = useState(action.status || "Open");
  const [notes, setNotes] = useState(action.notes || "");

  const updateMutation = useMutation({
    mutationFn: () => updateWorkshopAction(action.id, {
      action_text: actionText,
      owner_name: ownerName,
      due_date: dueDate || null,
      status,
      notes,
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workshop", workshopId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteWorkshopAction(action.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workshop", workshopId] }),
  });

  return (
    <div className="mvp18-action-row">
      <label className="mvp18-action-field">
        Action
        <textarea value={actionText} rows={3} onChange={(event) => setActionText(event.target.value)} />
      </label>
      <div className="mvp18-form-grid">
        <label>
          Owner
          <input value={ownerName} onChange={(event) => setOwnerName(event.target.value)} />
        </label>
        <label>
          Due Date
          <input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />
        </label>
        <label>
          Status
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="Open">Open</option>
            <option value="In Progress">In Progress</option>
            <option value="Closed">Closed</option>
          </select>
        </label>
      </div>
      <label className="mvp18-action-field">
        Notes
        <textarea value={notes} rows={2} onChange={(event) => setNotes(event.target.value)} />
      </label>
      <div className="mvp18-actions">
        <button className="mvp18-button-secondary" type="button" onClick={() => updateMutation.mutate()}>
          Save Action
        </button>
        <button
          className="mvp18-button-danger"
          type="button"
          onClick={() => {
            const ok = window.confirm("Delete this workshop action?");
            if (ok) deleteMutation.mutate();
          }}
        >
          Delete
        </button>
      </div>
    </div>
  );
}

function WorkshopDetailPage({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const [formState, setFormState] = useState<WorkshopFormState | null>(null);
  const [promptPreview, setPromptPreview] = useState<PromptPreview | null>(null);
  const [meetingNotes, setMeetingNotes] = useState("");
  const [keyDecisions, setKeyDecisions] = useState("");
  const [newActionText, setNewActionText] = useState("");
  const [newOwnerName, setNewOwnerName] = useState("");

  const query = useQuery({ queryKey: ["workshop", id], queryFn: () => getWorkshop(id), retry: 1 });

  useEffect(() => {
    if (query.data) {
      setMeetingNotes(query.data.meeting_notes || "");
      setKeyDecisions(query.data.key_decisions || "");
    }
  }, [query.data?.id, query.data?.meeting_notes, query.data?.key_decisions]);

  const updateMutation = useMutation({
    mutationFn: (payload: WorkshopFormPayload) => updateWorkshop(id, payload),
    onSuccess: () => {
      setFormState(null);
      queryClient.invalidateQueries({ queryKey: ["workshop", id] });
      queryClient.invalidateQueries({ queryKey: ["workshops"] });
    },
  });

  const analyzeMutation = useMutation({
    mutationFn: () => analyzeWorkshop(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workshop", id] });
      queryClient.invalidateQueries({ queryKey: ["workshops"] });
    },
  });

  const saveAnalysisMutation = useMutation({
    mutationFn: () => updateWorkshopAnalysis(id, { meeting_notes: meetingNotes, key_decisions: keyDecisions }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workshop", id] }),
  });

  const addActionMutation = useMutation({
    mutationFn: () => createWorkshopAction(id, {
      action_text: newActionText,
      owner_name: newOwnerName,
      status: "Open",
      notes: null,
      due_date: null,
      order_index: query.data?.actions.length || 0,
    }),
    onSuccess: () => {
      setNewActionText("");
      setNewOwnerName("");
      queryClient.invalidateQueries({ queryKey: ["workshop", id] });
      queryClient.invalidateQueries({ queryKey: ["workshops"] });
    },
  });

  if (query.isLoading) return <LoadingPanel label="Loading workshop..." />;
  if (query.isError) return <ErrorPanel error={query.error} />;

  const workshop = query.data as Workshop;

  return (
    <>
      <div className="mvp18-page-header">
        <div>
          <h1>{workshop.title}</h1>
          <div className="mvp18-entity-meta">
            <span>Date: {formatDate(workshop.workshop_date)}</span>
            <span>Track: {workshop.functional_track || "-"}</span>
            <span>Duration: {formatHours(workshop.duration_hours)}</span>
            <span>Transcript: {workshop.transcript_filename || "-"}</span>
            <span>Analyzed: {workshop.last_analyzed_at ? "Yes" : "No"}</span>
          </div>
        </div>
        <div className="mvp18-actions">
          <button className="mvp18-button-secondary" onClick={() => setFormState({ mode: "edit", item: workshop })}>Edit</button>
          <button
            className="mvp18-button-secondary"
            onClick={async () => setPromptPreview(await getWorkshopPromptPreview(id))}
          >
            Show Prompts
          </button>
          <button className="mvp18-button-primary" disabled={!workshop.transcript_text || analyzeMutation.isPending} onClick={() => analyzeMutation.mutate()}>
            {analyzeMutation.isPending ? "Analyzing..." : "Analyze Transcript"}
          </button>
        </div>
      </div>

      {analyzeMutation.isError ? <ErrorPanel error={analyzeMutation.error} /> : null}

      <section className="mvp18-panel">
        <div className="mvp18-section-header">
          <div>
            <h2>Workshop Details</h2>
            <p>{workshop.recording_path ? `Recording path: ${workshop.recording_path}` : "No recording path saved."}</p>
          </div>
        </div>
        <div className="mvp18-detail-grid">
          <div>
            <h3>Participants</h3>
            <pre>{workshop.participants_text || "-"}</pre>
          </div>
          <div>
            <h3>Agenda</h3>
            <pre>{workshop.agenda || "-"}</pre>
          </div>
        </div>
      </section>

      <section className="mvp18-panel">
        <div className="mvp18-section-header">
          <div>
            <h2>Meeting Notes</h2>
            <p>Editable output from transcript analysis.</p>
          </div>
          <button className="mvp18-button-primary" onClick={() => saveAnalysisMutation.mutate()}>Save Notes</button>
        </div>
        <div className="mvp18-form">
          <label>
            Notes
            <textarea value={meetingNotes} rows={18} onChange={(event) => setMeetingNotes(event.target.value)} />
          </label>
          <label>
            Key Decisions
            <textarea value={keyDecisions} rows={5} onChange={(event) => setKeyDecisions(event.target.value)} />
          </label>
        </div>
      </section>

      <section className="mvp18-panel">
        <div className="mvp18-section-header">
          <div>
            <h2>Actions</h2>
            <p>Editable action items and owners.</p>
          </div>
          <StatusBadge status={`${workshop.actions.length} actions`} />
        </div>
        <div className="mvp18-action-list">
          {workshop.actions.length === 0 ? <EmptyPanel label="No actions yet." /> : null}
          {workshop.actions.map((action) => (
            <WorkshopActionRow key={action.id} action={action} workshopId={id} />
          ))}
        </div>
        <div className="mvp18-action-row">
          <label>
            New Action
            <textarea value={newActionText} rows={2} onChange={(event) => setNewActionText(event.target.value)} />
          </label>
          <label>
            Owner
            <input value={newOwnerName} onChange={(event) => setNewOwnerName(event.target.value)} />
          </label>
          <div className="mvp18-actions">
            <button className="mvp18-button-primary" disabled={!newActionText.trim()} onClick={() => addActionMutation.mutate()}>
              Add Action
            </button>
          </div>
        </div>
      </section>

      {formState ? (
        <WorkshopFormModal
          state={formState}
          onClose={() => setFormState(null)}
          onSubmit={(payload) => updateMutation.mutate(payload)}
        />
      ) : null}

      {promptPreview ? <PromptPreviewModal preview={promptPreview} onClose={() => setPromptPreview(null)} /> : null}
    </>
  );
}

function SettingsPage() {
  const queryClient = useQueryClient();
  const promptsQuery = useQuery({ queryKey: ["llm-prompts"], queryFn: getLlmPrompts, retry: 1 });
  const [selectedPromptKey, setSelectedPromptKey] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [userPromptTemplate, setUserPromptTemplate] = useState("");

  const prompts = promptsQuery.data ?? [];
  const selectedPrompt = prompts.find((prompt) => prompt.prompt_key === selectedPromptKey) || prompts[0];

  useEffect(() => {
    if (!selectedPromptKey && prompts[0]) {
      setSelectedPromptKey(prompts[0].prompt_key);
    }
  }, [prompts, selectedPromptKey]);

  useEffect(() => {
    if (selectedPrompt) {
      setName(selectedPrompt.name);
      setDescription(selectedPrompt.description || "");
      setSystemPrompt(selectedPrompt.system_prompt);
      setUserPromptTemplate(selectedPrompt.user_prompt_template);
    }
  }, [selectedPrompt?.prompt_key]);

  const updateMutation = useMutation({
    mutationFn: () => updateLlmPrompt(selectedPrompt.prompt_key, {
      name,
      description,
      system_prompt: systemPrompt,
      user_prompt_template: userPromptTemplate,
      is_active: selectedPrompt.is_active,
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["llm-prompts"] }),
  });

  if (promptsQuery.isLoading) return <LoadingPanel label="Loading settings..." />;
  if (promptsQuery.isError) return <ErrorPanel error={promptsQuery.error} />;

  return (
    <>
      <div className="mvp18-page-header">
        <div>
          <h1>Settings</h1>
          <p>Manage LLM system and user prompts used by cockpit analysis features.</p>
        </div>
      </div>

      <section className="mvp18-panel">
        <div className="mvp18-section-header">
          <div>
            <h2>Prompt Library</h2>
            <p>Prompt variables use double braces, such as {"{{transcript_text}}"}.</p>
          </div>
          <StatusBadge status={`${prompts.length} prompts`} />
        </div>

        {selectedPrompt ? (
          <div className="mvp18-form">
            <label>
              Prompt
              <select value={selectedPrompt.prompt_key} onChange={(event) => setSelectedPromptKey(event.target.value)}>
                {prompts.map((prompt: LlmPromptTemplate) => (
                  <option key={prompt.prompt_key} value={prompt.prompt_key}>{prompt.name}</option>
                ))}
              </select>
            </label>

            <label>
              Name
              <input value={name} onChange={(event) => setName(event.target.value)} />
            </label>

            <label>
              Description
              <textarea value={description} rows={3} onChange={(event) => setDescription(event.target.value)} />
            </label>

            <label>
              System Prompt
              <textarea value={systemPrompt} rows={8} onChange={(event) => setSystemPrompt(event.target.value)} />
            </label>

            <label>
              User Prompt Template
              <textarea value={userPromptTemplate} rows={14} onChange={(event) => setUserPromptTemplate(event.target.value)} />
            </label>

            <div className="mvp18-actions">
              <button className="mvp18-button-primary" onClick={() => updateMutation.mutate()} disabled={updateMutation.isPending}>
                {updateMutation.isPending ? "Saving..." : "Save Prompt"}
              </button>
            </div>
          </div>
        ) : (
          <EmptyPanel label="No prompt templates available." />
        )}
      </section>
    </>
  );
}

function EngagementsPage({ setFormState }: { setFormState: (state: FormState | null) => void }) {
  const queryClient = useQueryClient();
  const engagementsQuery = useQuery({ queryKey: ["mvp18-engagements"], queryFn: getEngagements, retry: 1 });

  const deleteMutation = useMutation({
    mutationFn: deleteEngagement,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mvp18-engagements"] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-dashboard-status-summary"] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-reminder-indicator"] });
    },
  });

  if (engagementsQuery.isLoading) return <LoadingPanel label="Loading engagements..." />;
  if (engagementsQuery.isError) return <ErrorPanel error={engagementsQuery.error} />;

  const items = engagementsQuery.data ?? [];

  return (
    <>
      <div className="mvp18-page-header">
        <div>
          <h1>Engagements</h1>
          <p>Select an engagement to see its related workstreams.</p>
        </div>
      </div>

      <div className="mvp18-list">
        {items.length === 0 ? <EmptyPanel label="No engagements yet." /> : null}
        {items.map((item) => (
          <EntityCard
            key={item.id}
            item={item}
            viewLabel="View"
            deleteLabel="Delete"
            onView={() => navigateTo(`/engagements/${item.id}`)}
            onEdit={() => setFormState({ mode: "edit", entityKind: "engagement", item })}
            onDelete={() => {
              const ok = window.confirm(
                "Are you sure you want to delete this engagement?\n\nThis will delete related workstreams, deliverables, tasks, sub-tasks, workspace records, files, reminders, and recommendations.\n\nThis action cannot be undone.",
              );
              if (ok) deleteMutation.mutate(item.id);
            }}
          />
        ))}
      </div>

      <div className="mvp18-panel">
        <button className="mvp18-button-primary" onClick={() => setFormState({ mode: "create", entityKind: "engagement" })}>
          Add Engagement
        </button>
      </div>
    </>
  );
}

function EngagementDetailPage({ id, setFormState }: { id: string; setFormState: (state: FormState | null) => void }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["mvp18-engagement-workspace", id], queryFn: () => getEngagementWorkspace(id), retry: 1 });

  const deleteMutation = useMutation({
    mutationFn: deleteWorkstream,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mvp18-engagement-workspace", id] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-dashboard-status-summary"] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-reminder-indicator"] });
    },
  });

  if (query.isLoading) return <LoadingPanel label="Loading engagement workspace..." />;
  if (query.isError) return <ErrorPanel error={query.error} />;

  const workspace = query.data as EngagementWorkspace;

  return (
    <HierarchyChildrenPage
      title={entityLabel(workspace.engagement)}
      subtitle="Workstreams for this engagement."
      childrenLabel="Workstreams"
      items={workspace.workstreams}
      emptyLabel="No workstreams yet."
      addLabel="Add Workstream"
      viewLabel="View"
      onAdd={() => setFormState({ mode: "create", entityKind: "workstream", parentId: workspace.engagement.id })}
      onView={(item) => navigateTo(`/workstreams/${item.id}`)}
      onEdit={(item) => setFormState({ mode: "edit", entityKind: "workstream", item })}
      onDelete={(item) => {
        const ok = window.confirm(
          "Are you sure you want to delete this workstream?\n\nThis will delete related deliverables, tasks, sub-tasks, workspace records, files, reminders, and recommendations.\n\nThis action cannot be undone.",
        );
        if (ok) deleteMutation.mutate(item.id);
      }}
    />
  );
}

function WorkstreamDetailPage({ id, setFormState }: { id: string; setFormState: (state: FormState | null) => void }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["mvp18-workstream-workspace", id], queryFn: () => getWorkstreamWorkspace(id), retry: 1 });

  const deleteMutation = useMutation({
    mutationFn: deleteDeliverable,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mvp18-workstream-workspace", id] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-dashboard-status-summary"] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-reminder-indicator"] });
    },
  });

  if (query.isLoading) return <LoadingPanel label="Loading workstream workspace..." />;
  if (query.isError) return <ErrorPanel error={query.error} />;

  const workspace = query.data as WorkstreamWorkspace;

  return (
    <HierarchyChildrenPage
      title={entityLabel(workspace.workstream)}
      subtitle="Deliverables for this workstream."
      childrenLabel="Deliverables"
      items={workspace.deliverables}
      emptyLabel="No deliverables yet."
      addLabel="Add Deliverable"
      viewLabel="View"
      onAdd={() => setFormState({ mode: "create", entityKind: "deliverable", parentId: workspace.workstream.id })}
      onView={(item) => navigateTo(`/deliverables/${item.id}`)}
      onEdit={(item) => setFormState({ mode: "edit", entityKind: "deliverable", item })}
      onDelete={(item) => {
        const ok = window.confirm(
          "Are you sure you want to delete this deliverable?\n\nThis will delete related tasks, sub-tasks, workspace records, files, reminders, and recommendations.\n\nThis action cannot be undone.",
        );
        if (ok) deleteMutation.mutate(item.id);
      }}
    />
  );
}

function DeliverableDetailPage({ id, setFormState }: { id: string; setFormState: (state: FormState | null) => void }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["mvp18-deliverable-workspace", id], queryFn: () => getDeliverableWorkspace(id), retry: 1 });

  const deleteMutation = useMutation({
    mutationFn: deleteTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mvp18-deliverable-workspace", id] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-dashboard-status-summary"] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-reminder-indicator"] });
    },
  });

  if (query.isLoading) return <LoadingPanel label="Loading deliverable workspace..." />;
  if (query.isError) return <ErrorPanel error={query.error} />;

  const workspace = query.data as DeliverableWorkspace;

  return (
    <HierarchyChildrenPage
      title={entityLabel(workspace.deliverable)}
      subtitle="Tasks for this deliverable."
      childrenLabel="Tasks"
      items={workspace.tasks}
      emptyLabel="No tasks yet."
      addLabel="Add Task"
      viewLabel="Open Workspace"
      onAdd={() => setFormState({ mode: "create", entityKind: "task", parentId: workspace.deliverable.id })}
      onView={(item) => navigateTo(`/tasks/${item.id}`)}
      onEdit={(item) => setFormState({ mode: "edit", entityKind: "task", item })}
      onDelete={(item) => {
        const ok = window.confirm(
          "Are you sure you want to delete this task?\n\nThis will delete related sub-tasks, workspace records, files, reminders, and recommendations.\n\nThis action cannot be undone.",
        );
        if (ok) deleteMutation.mutate(item.id);
      }}
    />
  );
}

function HierarchyChildrenPage({
  title,
  subtitle,
  childrenLabel,
  items,
  emptyLabel,
  addLabel,
  viewLabel,
  onAdd,
  onView,
  onEdit,
  onDelete,
}: {
  title: string;
  subtitle: string;
  childrenLabel: string;
  items: EntitySummary[];
  emptyLabel: string;
  addLabel: string;
  viewLabel: string;
  onAdd: () => void;
  onView: (item: EntitySummary) => void;
  onEdit: (item: EntitySummary) => void;
  onDelete: (item: EntitySummary) => void;
}) {
  return (
    <>
      <div className="mvp18-page-header">
        <div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
      </div>

      <section className="mvp18-panel">
        <h2>{childrenLabel}</h2>
        <div className="mvp18-list">
          {items.length === 0 ? <EmptyPanel label={emptyLabel} /> : null}
          {items.map((item) => (
            <EntityCard
              key={item.id}
              item={item}
              viewLabel={viewLabel}
              deleteLabel="Delete"
              onView={() => onView(item)}
              onEdit={() => onEdit(item)}
              onDelete={() => onDelete(item)}
            />
          ))}
        </div>
      </section>

      <div className="mvp18-panel">
        <button className="mvp18-button-primary" onClick={onAdd}>{addLabel}</button>
      </div>
    </>
  );
}

function WorkspaceRecordCards({ counts }: { counts: Record<string, number> }) {
  const items = [
    ["Data Collections", counts.data_collections],
    ["Questions", counts.questions],
    ["Findings", counts.findings],
    ["Analysis", counts.analysis],
    ["Evidence", counts.evidence],
    ["Files", counts.files],
    ["Recommendations", counts.recommendations],
    ["Reminders", counts.reminders],
  ];

  return (
    <div className="mvp18-card-grid">
      {items.map(([label, value]) => (
        <div className="mvp18-summary-card" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function TaskWorkspacePage({ id, setFormState }: { id: string; setFormState: (state: FormState | null) => void }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["mvp18-task-workspace", id], queryFn: () => getTaskWorkspace(id), retry: 1 });

  const deleteMutation = useMutation({
    mutationFn: deleteSubtask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mvp18-task-workspace", id] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-dashboard-status-summary"] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-reminder-indicator"] });
    },
  });

  if (query.isLoading) return <LoadingPanel label="Loading task workspace..." />;
  if (query.isError) return <ErrorPanel error={query.error} />;

  const workspace = query.data as TaskWorkspace;

  return (
    <>
      <div className="mvp18-page-header">
        <div>
          <h1>{entityLabel(workspace.task)}</h1>
          <TaskDescriptionDetails description={workspace.task.description || "Task workspace"} />
          <div className="mvp18-entity-meta">
            <StatusBadge status={workspace.task.status} />
            <span>Owner: {workspace.task.owner_name || "-"}</span>
            <span>Target: {formatDate(workspace.task.target_date)}</span>
          </div>
        </div>
      </div>

      <WorkspaceRecordCards counts={workspace.record_counts} />

      <HierarchyChildrenPage
        title="Sub-tasks"
        subtitle="Sub-tasks for this task."
        childrenLabel="Sub-tasks"
        items={workspace.subtasks}
        emptyLabel="No sub-tasks yet."
        addLabel="Add Sub-task"
        viewLabel="Open Workspace"
        onAdd={() => setFormState({ mode: "create", entityKind: "subtask", parentId: workspace.task.id })}
        onView={(item) => navigateTo(`/subtasks/${item.id}`)}
        onEdit={(item) => setFormState({ mode: "edit", entityKind: "subtask", item })}
        onDelete={(item) => {
          const ok = window.confirm(
            "Are you sure you want to delete this sub-task?\n\nThis will delete related workspace records, files, reminders, and recommendations.\n\nThis action cannot be undone.",
          );
          if (ok) deleteMutation.mutate(item.id);
        }}
      />

      <Mvp18WorkspacePanel scopeType="task" scopeId={workspace.task.id} />
    </>
  );
}

function SubtaskWorkspacePage({ id }: { id: string }) {
  const query = useQuery({ queryKey: ["mvp18-subtask-workspace", id], queryFn: () => getSubtaskWorkspace(id), retry: 1 });

  if (query.isLoading) return <LoadingPanel label="Loading sub-task workspace..." />;
  if (query.isError) return <ErrorPanel error={query.error} />;

  const workspace = query.data as SubtaskWorkspace;

  return (
    <>
      <div className="mvp18-page-header">
        <div>
          <h1>{entityLabel(workspace.subtask)}</h1>
          <p>{workspace.subtask.description || "Sub-task workspace"}</p>
          <div className="mvp18-entity-meta">
            <StatusBadge status={workspace.subtask.status} />
            <span>Owner: {workspace.subtask.owner_name || "-"}</span>
            <span>Target: {formatDate(workspace.subtask.target_date)}</span>
          </div>
        </div>
      </div>

      <WorkspaceRecordCards counts={workspace.record_counts} />
      <Mvp18WorkspacePanel scopeType="subtask" scopeId={workspace.subtask.id} />
    </>
  );
}

function myWorkEntityPath(entityKind: MyWorkListEntityKind, itemId: string): string {
  if (entityKind === "workstream") return `/my-work/workstreams/${itemId}`;
  if (entityKind === "deliverable") return `/my-work/deliverables/${itemId}`;
  return `/my-work/tasks/${itemId}`;
}

function deleteMyWorkEntity(entityKind: MyWorkListEntityKind, itemId: string) {
  if (entityKind === "workstream") return deleteWorkstream(itemId);
  if (entityKind === "deliverable") return deleteDeliverable(itemId);
  return deleteTask(itemId);
}

function myWorkDeletePrompt(entityKind: MyWorkListEntityKind): string {
  if (entityKind === "workstream") {
    return "Are you sure you want to delete this workstream?\n\nThis will delete related deliverables, tasks, sub-tasks, workspace records, files, reminders, and recommendations.\n\nThis action cannot be undone.";
  }

  if (entityKind === "deliverable") {
    return "Are you sure you want to delete this deliverable?\n\nThis will delete related tasks, sub-tasks, workspace records, files, reminders, and recommendations.\n\nThis action cannot be undone.";
  }

  return "Are you sure you want to delete this task?\n\nThis will delete related sub-tasks, workspace records, files, reminders, and recommendations.\n\nThis action cannot be undone.";
}

function MyWorkSection({
  title,
  subtitle,
  items,
  entityKind,
  emptyLabel,
  setFormState,
}: {
  title: string;
  subtitle: string;
  items: EntitySummary[];
  entityKind: MyWorkListEntityKind;
  emptyLabel: string;
  setFormState: (state: FormState | null) => void;
}) {
  const queryClient = useQueryClient();
  const entityLabels = MY_WORK_ENTITY_LABELS[entityKind];
  const deleteMutation = useMutation({
    mutationFn: (itemId: string) => deleteMyWorkEntity(entityKind, itemId),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  return (
    <section className="mvp18-panel mvp18-mywork-section">
      <div className="mvp18-section-header">
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
        <StatusBadge status={`${items.length} ${items.length === 1 ? entityLabels.singular : entityLabels.plural}`} />
      </div>

      {items.length === 0 ? (
        <div className="mvp18-empty">{emptyLabel}</div>
      ) : (
        <div className="mvp18-entity-list">
          {items.map((item) => (
            <EntityCard
              key={item.id}
              item={item}
              viewLabel="View"
              deleteLabel="Delete"
              onView={() => navigateTo(myWorkEntityPath(entityKind, item.id))}
              onEdit={() => setFormState({ mode: "edit", entityKind, item })}
              onDelete={() => {
                const ok = window.confirm(myWorkDeletePrompt(entityKind));
                if (ok) deleteMutation.mutate(item.id);
              }}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function MyWorkPage({ setFormState }: { setFormState: (state: FormState | null) => void }) {
  const ownerName = getMyWorkOwnerName();
  const [selectedListKey, setSelectedListKey] = useState<MyWorkListKey>("primary_workstreams");
  const query = useQuery({
    queryKey: ["mvp18-my-work", ownerName],
    queryFn: () => getMyWork(ownerName),
    retry: 1,
  });

  if (query.isLoading) return <LoadingPanel label="Loading My Work..." />;
  if (query.isError) return <ErrorPanel error={query.error} />;

  const data = query.data as MyWorkResponse;
  const listOptions = MY_WORK_LIST_CONFIGS.map((config) => ({
    ...config,
    count: data.counts[config.key],
    items: data[config.key],
  }));
  const selectedOption = listOptions.find((option) => option.key === selectedListKey) || listOptions[0];

  return (
    <>
      <div className="mvp18-page-header">
        <div>
          <h1>My Work</h1>
          <p>Personalized view for {data.owner_name} across workstreams, deliverables, and tasks.</p>
        </div>
      </div>

      <div className="mvp18-card-grid">
        {listOptions.map((option) => (
          <button
            key={option.key}
            type="button"
            className={`mvp18-summary-card mvp18-mywork-tile${option.key === selectedOption.key ? " active" : ""}`}
            aria-pressed={option.key === selectedOption.key}
            onClick={() => setSelectedListKey(option.key)}
          >
            <span>{option.label}</span>
            <strong>{option.count}</strong>
            <div className="mvp18-status-row">{option.helper}</div>
          </button>
        ))}
      </div>

      <MyWorkSection
        title={selectedOption.sectionTitle}
        subtitle={`${selectedOption.label} tagged to ${data.owner_name}.`}
        items={selectedOption.items}
        entityKind={selectedOption.entityKind}
        emptyLabel={selectedOption.emptyLabel}
        setFormState={setFormState}
      />
    </>
  );
}



function MyWorkWorkstreamDetailPage({ id, setFormState }: { id: string; setFormState: (state: FormState | null) => void }) {
  const queryClient = useQueryClient();
  const ownerName = getMyWorkOwnerName();
  const query = useQuery({
    queryKey: ["mvp18-my-work-workstream-workspace", id, ownerName],
    queryFn: () => getMyWorkWorkstreamWorkspace(id, ownerName),
    retry: 1,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDeliverable,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mvp18-my-work-workstream-workspace", id] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-my-work"] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-dashboard-status-summary"] });
    },
  });

  if (query.isLoading) return <LoadingPanel label="Loading My Work workstream..." />;
  if (query.isError) return <ErrorPanel error={query.error} />;

  const workspace = query.data as WorkstreamWorkspace;
  const workspaceOwnerName = workspace.owner_name || ownerName;

  return (
    <HierarchyChildrenPage
      title={entityLabel(workspace.workstream)}
      subtitle={`My Work view: only deliverables where ${workspaceOwnerName} is primary or secondary/support are shown.`}
      childrenLabel="My Deliverables"
      items={workspace.deliverables}
      emptyLabel={`No deliverables tagged to ${workspaceOwnerName} under this workstream.`}
      addLabel="Add Deliverable"
      viewLabel="View"
      onAdd={() => setFormState({ mode: "create", entityKind: "deliverable", parentId: workspace.workstream.id })}
      onView={(item) => navigateTo(`/my-work/deliverables/${item.id}`)}
      onEdit={(item) => setFormState({ mode: "edit", entityKind: "deliverable", item })}
      onDelete={(item) => {
        const ok = window.confirm(
          "Are you sure you want to delete this deliverable?\n\nThis will delete related tasks, sub-tasks, workspace records, files, reminders, and recommendations.\n\nThis action cannot be undone.",
        );
        if (ok) deleteMutation.mutate(item.id);
      }}
    />
  );
}

function MyWorkDeliverableDetailPage({ id, setFormState }: { id: string; setFormState: (state: FormState | null) => void }) {
  const queryClient = useQueryClient();
  const ownerName = getMyWorkOwnerName();
  const query = useQuery({
    queryKey: ["mvp18-my-work-deliverable-workspace", id, ownerName],
    queryFn: () => getMyWorkDeliverableWorkspace(id, ownerName),
    retry: 1,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mvp18-my-work-deliverable-workspace", id] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-my-work"] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-dashboard-status-summary"] });
    },
  });

  if (query.isLoading) return <LoadingPanel label="Loading My Work deliverable..." />;
  if (query.isError) return <ErrorPanel error={query.error} />;

  const workspace = query.data as DeliverableWorkspace;
  const workspaceOwnerName = workspace.owner_name || ownerName;

  return (
    <HierarchyChildrenPage
      title={entityLabel(workspace.deliverable)}
      subtitle={`My Work view: only tasks where ${workspaceOwnerName} is primary or secondary/support are shown.`}
      childrenLabel="My Tasks"
      items={workspace.tasks}
      emptyLabel={`No tasks tagged to ${workspaceOwnerName} under this deliverable.`}
      addLabel="Add Task"
      viewLabel="Open Workspace"
      onAdd={() => setFormState({ mode: "create", entityKind: "task", parentId: workspace.deliverable.id })}
      onView={(item) => navigateTo(`/my-work/tasks/${item.id}`)}
      onEdit={(item) => setFormState({ mode: "edit", entityKind: "task", item })}
      onDelete={(item) => {
        const ok = window.confirm(
          "Are you sure you want to delete this task?\n\nThis will delete related sub-tasks, workspace records, files, reminders, and recommendations.\n\nThis action cannot be undone.",
        );
        if (ok) deleteMutation.mutate(item.id);
      }}
    />
  );
}

function MyWorkTaskWorkspacePage({ id, setFormState }: { id: string; setFormState: (state: FormState | null) => void }) {
  const queryClient = useQueryClient();
  const ownerName = getMyWorkOwnerName();
  const query = useQuery({
    queryKey: ["mvp18-my-work-task-workspace", id, ownerName],
    queryFn: () => getMyWorkTaskWorkspace(id, ownerName),
    retry: 1,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteSubtask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mvp18-my-work-task-workspace", id] });
      queryClient.invalidateQueries({ queryKey: ["mvp18-dashboard-status-summary"] });
    },
  });

  if (query.isLoading) return <LoadingPanel label="Loading My Work task workspace..." />;
  if (query.isError) return <ErrorPanel error={query.error} />;

  const workspace = query.data as TaskWorkspace;

  return (
    <>
      <div className="mvp18-page-header">
        <div>
          <h1>{entityLabel(workspace.task)}</h1>
          <TaskDescriptionDetails description={workspace.task.description || "Task workspace"} />
          <div className="mvp18-entity-meta">
            <StatusBadge status={workspace.task.status} />
            <span>Primary: {workspace.task.owner_name || "-"}</span>
            {workspace.task.secondary_owner_name ? <span>Secondary: {workspace.task.secondary_owner_name}</span> : null}
            <span>Target: {formatDate(workspace.task.target_date)}</span>
          </div>
        </div>
      </div>

      <WorkspaceRecordCards counts={workspace.record_counts} />

      <HierarchyChildrenPage
        title="Sub-tasks"
        subtitle="Sub-tasks for this My Work task. Sub-tasks are shown because the parent task is tagged to you."
        childrenLabel="Sub-tasks"
        items={workspace.subtasks}
        emptyLabel="No sub-tasks yet."
        addLabel="Add Sub-task"
        viewLabel="Open Workspace"
        onAdd={() => setFormState({ mode: "create", entityKind: "subtask", parentId: workspace.task.id })}
        onView={(item) => navigateTo(`/my-work/subtasks/${item.id}`)}
        onEdit={(item) => setFormState({ mode: "edit", entityKind: "subtask", item })}
        onDelete={(item) => {
          const ok = window.confirm(
            "Are you sure you want to delete this sub-task?\n\nThis will delete related workspace records, files, reminders, and recommendations.\n\nThis action cannot be undone.",
          );
          if (ok) deleteMutation.mutate(item.id);
        }}
      />

      <Mvp18WorkspacePanel scopeType="task" scopeId={workspace.task.id} />
    </>
  );
}

function MyWorkSubtaskWorkspacePage({ id }: { id: string }) {
  const ownerName = getMyWorkOwnerName();
  const query = useQuery({
    queryKey: ["mvp18-my-work-subtask-workspace", id, ownerName],
    queryFn: () => getMyWorkSubtaskWorkspace(id, ownerName),
    retry: 1,
  });

  if (query.isLoading) return <LoadingPanel label="Loading My Work sub-task workspace..." />;
  if (query.isError) return <ErrorPanel error={query.error} />;

  const workspace = query.data as SubtaskWorkspace;

  return (
    <>
      <div className="mvp18-page-header">
        <div>
          <h1>{entityLabel(workspace.subtask)}</h1>
          <TaskDescriptionDetails description={workspace.subtask.description || "Sub-task workspace"} />
          <div className="mvp18-entity-meta">
            <StatusBadge status={workspace.subtask.status} />
            <span>Primary: {workspace.subtask.owner_name || "-"}</span>
            {workspace.subtask.secondary_owner_name ? <span>Secondary: {workspace.subtask.secondary_owner_name}</span> : null}
            <span>Target: {formatDate(workspace.subtask.target_date)}</span>
          </div>
        </div>
      </div>

      <WorkspaceRecordCards counts={workspace.record_counts} />
      <Mvp18WorkspacePanel scopeType="subtask" scopeId={workspace.subtask.id} />
    </>
  );
}

function PlaceholderPage({ title, message }: { title: string; message: string }) {
  return (
    <div className="mvp18-panel">
      <h1>{title}</h1>
      <p>{message}</p>
    </div>
  );
}

function getBreadcrumbQueryConfig(route: RouteState): BreadcrumbQueryConfig | null {
  const [section, id] = route.parts;

  if (!id) return null;

  if (section === "engagements") {
    return {
      queryKey: ["mvp18-engagement-workspace", id],
      queryFn: () => getEngagementWorkspace(id),
    };
  }

  if (section === "workstreams") {
    return {
      queryKey: ["mvp18-workstream-workspace", id],
      queryFn: () => getWorkstreamWorkspace(id),
    };
  }

  if (section === "deliverables") {
    return {
      queryKey: ["mvp18-deliverable-workspace", id],
      queryFn: () => getDeliverableWorkspace(id),
    };
  }

  if (section === "tasks") {
    return {
      queryKey: ["mvp18-task-workspace", id],
      queryFn: () => getTaskWorkspace(id),
    };
  }

  if (section === "subtasks") {
    return {
      queryKey: ["mvp18-subtask-workspace", id],
      queryFn: () => getSubtaskWorkspace(id),
    };
  }

  if (section === "workshops") {
    return {
      queryKey: ["workshop", id],
      queryFn: () => getWorkshop(id),
    };
  }

  if (section === "my-work") {
    const level = route.parts[1];
    const entityId = route.parts[2];
    const ownerName = getMyWorkOwnerName();

    if (!level || !entityId) return null;

    if (level === "workstreams") {
      return {
        queryKey: ["mvp18-my-work-workstream-workspace", entityId, ownerName],
        queryFn: () => getMyWorkWorkstreamWorkspace(entityId, ownerName),
      };
    }

    if (level === "deliverables") {
      return {
        queryKey: ["mvp18-my-work-deliverable-workspace", entityId, ownerName],
        queryFn: () => getMyWorkDeliverableWorkspace(entityId, ownerName),
      };
    }

    if (level === "tasks") {
      return {
        queryKey: ["mvp18-my-work-task-workspace", entityId, ownerName],
        queryFn: () => getMyWorkTaskWorkspace(entityId, ownerName),
      };
    }

    if (level === "subtasks") {
      return {
        queryKey: ["mvp18-my-work-subtask-workspace", entityId, ownerName],
        queryFn: () => getMyWorkSubtaskWorkspace(entityId, ownerName),
      };
    }
  }

  return null;
}

function entityBreadcrumb(item: EntitySummary | null | undefined, fallback: string, path?: string): BreadcrumbViewItem {
  return {
    label: breadcrumbEntityLabel(item, fallback),
    ...(item && path ? { path } : {}),
  };
}

function buildPageBreadcrumb(route: RouteState, data: BreadcrumbWorkspaceData): BreadcrumbViewItem[] {
  const [section, id] = route.parts;

  if (route.path === "/" || !section) return [];

  if (section === "login") {
    return [{ label: "Login" }];
  }

  if (section === "settings") {
    return [{ label: "Settings" }];
  }

  if (section === "workshops") {
    if (!id) return [{ label: "Workshops" }];
    const workshop = data as Workshop | null;
    return [
      { label: "Workshops", path: "/workshops" },
      { label: workshop?.title || "Workshop" },
    ];
  }

  if (section === "my-work") {
    const level = route.parts[1];
    const entityId = route.parts[2];
    const workspace = data as WorkstreamWorkspace | DeliverableWorkspace | TaskWorkspace | SubtaskWorkspace | null;

    if (!level || !entityId) {
      return [
        { label: "Engagements", path: "/engagements" },
        { label: "My Work" },
      ];
    }

    if (level === "workstreams") {
      return [
        { label: "Engagements", path: "/engagements" },
        { label: "My Work", path: "/my-work" },
        entityBreadcrumb((workspace as WorkstreamWorkspace | null)?.workstream, "Workstream"),
      ];
    }

    if (level === "deliverables") {
      const deliverableWorkspace = workspace as DeliverableWorkspace | null;
      return [
        { label: "Engagements", path: "/engagements" },
        { label: "My Work", path: "/my-work" },
        entityBreadcrumb(deliverableWorkspace?.deliverable, "Deliverable"),
      ];
    }

    if (level === "tasks") {
      const taskWorkspace = workspace as TaskWorkspace | null;
      return [
        { label: "Engagements", path: "/engagements" },
        { label: "My Work", path: "/my-work" },
        entityBreadcrumb(taskWorkspace?.task, "Task"),
      ];
    }

    if (level === "subtasks") {
      const subtaskWorkspace = workspace as SubtaskWorkspace | null;
      return [
        { label: "Engagements", path: "/engagements" },
        { label: "My Work", path: "/my-work" },
        entityBreadcrumb(subtaskWorkspace?.subtask, "Sub-task"),
      ];
    }

    return [{ label: "My Work", path: "/my-work" }];
  }

  if (section === "engagements") {
    if (!id) return [{ label: "Engagements" }];
    const workspace = data as EngagementWorkspace | null;
    return [
      { label: "Engagements", path: "/engagements" },
      entityBreadcrumb(workspace?.engagement, "Engagement"),
    ];
  }

  if (section === "workstreams") {
    if (!id) return [{ label: "Workstreams" }];
    const workspace = data as WorkstreamWorkspace | null;
    return [
      { label: "Engagements", path: "/engagements" },
      ...(workspace?.engagement ? [entityBreadcrumb(workspace.engagement, "Engagement", `/engagements/${workspace.engagement.id}`)] : []),
      { label: "Workstreams", path: "/workstreams" },
      entityBreadcrumb(workspace?.workstream, "Workstream"),
    ];
  }

  if (section === "deliverables") {
    if (!id) return [{ label: "Deliverables" }];
    const workspace = data as DeliverableWorkspace | null;
    return [
      { label: "Engagements", path: "/engagements" },
      ...(workspace?.engagement ? [entityBreadcrumb(workspace.engagement, "Engagement", `/engagements/${workspace.engagement.id}`)] : []),
      { label: "Workstreams", path: "/workstreams" },
      ...(workspace?.workstream ? [entityBreadcrumb(workspace.workstream, "Workstream", `/workstreams/${workspace.workstream.id}`)] : []),
      { label: "Deliverables", path: "/deliverables" },
      entityBreadcrumb(workspace?.deliverable, "Deliverable"),
    ];
  }

  if (section === "tasks") {
    if (!id) return [{ label: "Tasks" }];
    const workspace = data as TaskWorkspace | null;
    return [
      { label: "Engagements", path: "/engagements" },
      ...(workspace?.engagement ? [entityBreadcrumb(workspace.engagement, "Engagement", `/engagements/${workspace.engagement.id}`)] : []),
      { label: "Workstreams", path: "/workstreams" },
      ...(workspace?.workstream ? [entityBreadcrumb(workspace.workstream, "Workstream", `/workstreams/${workspace.workstream.id}`)] : []),
      { label: "Deliverables", path: "/deliverables" },
      ...(workspace?.deliverable ? [entityBreadcrumb(workspace.deliverable, "Deliverable", `/deliverables/${workspace.deliverable.id}`)] : []),
      { label: "Tasks", path: "/tasks" },
      entityBreadcrumb(workspace?.task, "Task"),
    ];
  }

  if (section === "subtasks") {
    if (!id) return [{ label: "Sub-tasks" }];
    const workspace = data as SubtaskWorkspace | null;
    return [
      { label: "Engagements", path: "/engagements" },
      ...(workspace?.engagement ? [entityBreadcrumb(workspace.engagement, "Engagement", `/engagements/${workspace.engagement.id}`)] : []),
      { label: "Workstreams", path: "/workstreams" },
      ...(workspace?.workstream ? [entityBreadcrumb(workspace.workstream, "Workstream", `/workstreams/${workspace.workstream.id}`)] : []),
      { label: "Deliverables", path: "/deliverables" },
      ...(workspace?.deliverable ? [entityBreadcrumb(workspace.deliverable, "Deliverable", `/deliverables/${workspace.deliverable.id}`)] : []),
      { label: "Tasks", path: "/tasks" },
      ...(workspace?.task ? [entityBreadcrumb(workspace.task, "Task", `/tasks/${workspace.task.id}`)] : []),
      { label: "Sub-tasks", path: "/subtasks" },
      entityBreadcrumb(workspace?.subtask, "Sub-task"),
    ];
  }

  return [{ label: section }];
}

function usePageBreadcrumb(route: RouteState): BreadcrumbViewItem[] {
  const breadcrumbQueryConfig = useMemo(() => getBreadcrumbQueryConfig(route), [route.path, route.parts]);
  const breadcrumbQuery = useQuery<BreadcrumbWorkspaceData>({
    queryKey: breadcrumbQueryConfig?.queryKey ?? ["mvp18-breadcrumb", "static", route.path],
    queryFn: breadcrumbQueryConfig?.queryFn ?? (() => Promise.resolve(null)),
    enabled: Boolean(breadcrumbQueryConfig),
    retry: 1,
  });

  return useMemo(
    () => buildPageBreadcrumb(route, breadcrumbQuery.data ?? null),
    [route.path, route.parts, breadcrumbQuery.data],
  );
}

function MainRouter({ setFormState }: { setFormState: (state: FormState | null) => void }) {
  const [route, setRoute] = useState<RouteState>(() => normalizePath());

  useEffect(() => {
    const handler = () => setRoute(normalizePath());
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);

  const parts = route.parts;

  if (route.path === "/" || parts.length === 0) return <DashboardPage />;
  if (parts[0] === "workshops" && parts.length === 1) return <WorkshopsPage />;
  if (parts[0] === "workshops" && parts[1]) return <WorkshopDetailPage id={parts[1]} />;
  if (parts[0] === "my-work" && parts.length === 1) return <MyWorkPage setFormState={setFormState} />;
  if (parts[0] === "my-work" && parts[1] === "workstreams" && parts[2]) {
    return <MyWorkWorkstreamDetailPage id={parts[2]} setFormState={setFormState} />;
  }
  if (parts[0] === "my-work" && parts[1] === "deliverables" && parts[2]) {
    return <MyWorkDeliverableDetailPage id={parts[2]} setFormState={setFormState} />;
  }
  if (parts[0] === "my-work" && parts[1] === "tasks" && parts[2]) {
    return <MyWorkTaskWorkspacePage id={parts[2]} setFormState={setFormState} />;
  }
  if (parts[0] === "my-work" && parts[1] === "subtasks" && parts[2]) {
    return <MyWorkSubtaskWorkspacePage id={parts[2]} />;
  }
  if (parts[0] === "engagements" && parts.length === 1) return <EngagementsPage setFormState={setFormState} />;
  if (parts[0] === "engagements" && parts[1]) return <EngagementDetailPage id={parts[1]} setFormState={setFormState} />;
  if (parts[0] === "workstreams" && parts.length === 1) {
    return (
      <GlobalEntityListPage
        title="Workstreams"
        subtitle="All workstreams across engagements. Select one to see related deliverables."
        queryKey="mvp18-all-workstreams"
        queryFn={getAllWorkstreams}
        pathPrefix="/workstreams"
        emptyLabel="No workstreams yet."
      />
    );
  }
  if (parts[0] === "workstreams" && parts[1]) return <WorkstreamDetailPage id={parts[1]} setFormState={setFormState} />;

  if (parts[0] === "deliverables" && parts.length === 1) {
    return (
      <GlobalEntityListPage
        title="Deliverables"
        subtitle="All deliverables across workstreams. Select one to see related tasks."
        queryKey="mvp18-all-deliverables"
        queryFn={getAllDeliverables}
        pathPrefix="/deliverables"
        emptyLabel="No deliverables yet."
      />
    );
  }
  if (parts[0] === "deliverables" && parts[1]) return <DeliverableDetailPage id={parts[1]} setFormState={setFormState} />;

  if (parts[0] === "tasks" && parts.length === 1) {
    return (
      <GlobalEntityListPage
        title="Tasks"
        subtitle="All tasks across deliverables. Select one to open its workspace."
        queryKey="mvp18-all-tasks"
        queryFn={getAllTasks}
        pathPrefix="/tasks"
        emptyLabel="No tasks yet."
      />
    );
  }
  if (parts[0] === "tasks" && parts[1]) return <TaskWorkspacePage id={parts[1]} setFormState={setFormState} />;

  if (parts[0] === "subtasks" && parts.length === 1) {
    return (
      <GlobalEntityListPage
        title="Sub-tasks"
        subtitle="All sub-tasks across tasks. Select one to open its workspace."
        queryKey="mvp18-all-subtasks"
        queryFn={getAllSubtasks}
        pathPrefix="/subtasks"
        emptyLabel="No sub-tasks yet."
      />
    );
  }
  if (parts[0] === "subtasks" && parts[1]) return <SubtaskWorkspacePage id={parts[1]} />;

  if (parts[0] === "tasks") {
    return <PlaceholderPage title="My Work" message="Select a task from a deliverable page. MVP 18C can add a dedicated My Work list." />;
  }

  if (parts[0] === "reminders") {
    return <PlaceholderPage title="Reminders" message="Use the reminder icon in the top right. A full reminders screen can be added after the simplified workspace is complete." />;
  }

  if (parts[0] === "reports") {
    return <PlaceholderPage title="Reports" message="Reports remain available in the previous MVP flow. MVP 18 focuses on simplifying the workspace flow first." />;
  }

  if (parts[0] === "operations") {
    return <PlaceholderPage title="Operations" message="Operations dashboard remains available in the previous MVP flow. It can be moved into this simplified shell after MVP 18C." />;
  }

  if (parts[0] === "settings") {
    return <SettingsPage />;
  }

  return <PlaceholderPage title="Page Not Found" message="The requested workspace route was not found." />;
}

function App() {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<StoredSession | null>(() => getStoredSession());
  const [formState, setFormState] = useState<FormState | null>(null);
  const [route, setRoute] = useState<RouteState>(() => normalizePath());

  useEffect(() => {
    const handler = () => setRoute(normalizePath());
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);

  const createMutation = useMutation({
    mutationFn: async (stateAndPayload: { state: FormState; payload: HierarchyFormPayload }) => {
      const { state, payload } = stateAndPayload;
      if (state.entityKind === "engagement") return createEngagement(payload);
      if (state.entityKind === "workstream" && state.parentId) return createWorkstream(state.parentId, payload);
      if (state.entityKind === "deliverable" && state.parentId) return createDeliverable(state.parentId, payload);
      if (state.entityKind === "task" && state.parentId) return createTask(state.parentId, payload);
      if (state.entityKind === "subtask" && state.parentId) return createSubtask(state.parentId, payload);
      throw new Error("Missing parent context for create action.");
    },
    onSuccess: () => {
      setFormState(null);
      queryClient.invalidateQueries();
    },
  });

  const updateMutation = useMutation({
    mutationFn: async (stateAndPayload: { state: FormState; payload: HierarchyFormPayload }) => {
      const { state, payload } = stateAndPayload;
      if (!state.item) throw new Error("Missing item for update action.");
      if (state.entityKind === "engagement") return updateEngagement(state.item.id, payload);
      if (state.entityKind === "workstream") return updateWorkstream(state.item.id, payload);
      if (state.entityKind === "deliverable") return updateDeliverable(state.item.id, payload);
      if (state.entityKind === "task") return updateTask(state.item.id, payload);
      if (state.entityKind === "subtask") return updateSubtask(state.item.id, payload);
      throw new Error("Unsupported update action.");
    },
    onSuccess: () => {
      setFormState(null);
      queryClient.invalidateQueries();
    },
  });

  if (!session) {
    if (route.path !== "/login") {
      window.location.replace("/login");
      return <LoadingPanel label="Opening login..." />;
    }

    return <LoginPage onLogin={setSession} />;
  }

  if (route.path === "/login") {
    window.location.replace("/");
    return <LoadingPanel label="Opening dashboard..." />;
  }

  const breadcrumb = usePageBreadcrumb(route);

  return (
    <AppShell session={session} setSession={setSession} breadcrumb={breadcrumb}>
      <MainRouter setFormState={setFormState} />

      {formState ? (
        <HierarchyFormModal
          state={formState}
          onClose={() => setFormState(null)}
          onSubmit={(payload) => {
            if (formState.mode === "create") {
              createMutation.mutate({ state: formState, payload });
            } else {
              updateMutation.mutate({ state: formState, payload });
            }
          }}
        />
      ) : null}

      {createMutation.isError ? <ErrorPanel error={createMutation.error} /> : null}
      {updateMutation.isError ? <ErrorPanel error={updateMutation.error} /> : null}
    </AppShell>
  );
}

export default App;
