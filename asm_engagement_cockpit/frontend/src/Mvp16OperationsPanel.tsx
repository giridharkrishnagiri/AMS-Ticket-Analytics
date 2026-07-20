import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  bootstrapCurrentUser,
  createAppUser,
  createAuditEvent,
  createExecutiveSnapshot,
  generateOperationNotifications,
  getAppUsers,
  getAuditEvents,
  getExecutiveSnapshots,
  getOperationsDashboard,
  getOperationNotifications,
  getRoles,
  updateOperationNotification,
  type AppUser,
  type AuditEvent,
  type ExecutiveSnapshot,
  type OperationNotification,
  type RoleDefinition,
} from "./operationsApi";

function StatusBadge({ status }: { status: string }) {
  return <span className="status-badge">{status}</span>;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "-";
  }

  return value.replace("T", " ").slice(0, 19);
}

function shortText(value: string, maxLength = 120) {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength)}...`;
}

function UsersTable({ users }: { users: AppUser[] }) {
  if (users.length === 0) {
    return <p className="empty-state">No application users yet. Use Bootstrap Current User first.</p>;
  }

  return (
    <div className="table-card wide-table">
      <table>
        <thead>
          <tr>
            <th>User</th>
            <th>Username</th>
            <th>Email</th>
            <th>Role</th>
            <th>Active</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {users.map((item) => (
            <tr key={item.id}>
              <td><strong>{item.display_name}</strong></td>
              <td>{item.username}</td>
              <td>{item.email ?? "-"}</td>
              <td>{item.role}</td>
              <td>{item.is_active ? "Yes" : "No"}</td>
              <td>{item.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RolesTable({ roles }: { roles: RoleDefinition[] }) {
  if (roles.length === 0) {
    return <p className="empty-state">No roles returned.</p>;
  }

  return (
    <div className="table-card wide-table">
      <table>
        <thead>
          <tr>
            <th>Role</th>
            <th>Permissions</th>
          </tr>
        </thead>
        <tbody>
          {roles.map((item) => (
            <tr key={item.role}>
              <td><strong>{item.role}</strong></td>
              <td>
                <ul className="compact-list">
                  {item.permissions.map((permission) => (
                    <li key={permission}>{permission}</li>
                  ))}
                </ul>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NotificationsTable({
  notifications,
  onMarkRead,
  onDismiss,
  isUpdating,
}: {
  notifications: OperationNotification[];
  onMarkRead: (id: string) => void;
  onDismiss: (id: string) => void;
  isUpdating: boolean;
}) {
  if (notifications.length === 0) {
    return <p className="empty-state">No notifications yet. Generate notifications from reminders.</p>;
  }

  return (
    <div className="table-card wide-table">
      <table>
        <thead>
          <tr>
            <th>Notification</th>
            <th>Severity</th>
            <th>Status</th>
            <th>Due</th>
            <th>Source</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {notifications.map((item) => (
            <tr key={item.id}>
              <td>
                <strong>{item.title}</strong>
                <div className="small-note">{shortText(item.message, 180)}</div>
              </td>
              <td>{item.severity}</td>
              <td><StatusBadge status={item.status} /></td>
              <td>{formatDateTime(item.due_date)}</td>
              <td>{item.source_type ?? "-"}</td>
              <td>
                <div className="button-row">
                  <button
                    className="secondary-button"
                    onClick={() => onMarkRead(item.id)}
                    disabled={isUpdating || item.status === "Read"}
                  >
                    Mark Read
                  </button>
                  <button
                    className="secondary-button"
                    onClick={() => onDismiss(item.id)}
                    disabled={isUpdating || item.status === "Dismissed"}
                  >
                    Dismiss
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditEventsTable({ auditEvents }: { auditEvents: AuditEvent[] }) {
  if (auditEvents.length === 0) {
    return <p className="empty-state">No audit events yet.</p>;
  }

  return (
    <div className="table-card wide-table">
      <table>
        <thead>
          <tr>
            <th>Event</th>
            <th>Category</th>
            <th>Actor</th>
            <th>Entity</th>
            <th>Severity</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {auditEvents.map((item) => (
            <tr key={item.id}>
              <td>
                <strong>{item.event_type}</strong>
                <div className="small-note">{item.description}</div>
              </td>
              <td>{item.event_category}</td>
              <td>{item.actor_name ?? "-"}</td>
              <td>{item.entity_title ?? item.entity_type ?? "-"}</td>
              <td>{item.severity}</td>
              <td>{formatDateTime(item.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ExecutiveSnapshotsTable({ snapshots }: { snapshots: ExecutiveSnapshot[] }) {
  if (snapshots.length === 0) {
    return <p className="empty-state">No executive snapshots yet.</p>;
  }

  return (
    <div className="table-card wide-table">
      <table>
        <thead>
          <tr>
            <th>Snapshot</th>
            <th>Health</th>
            <th>Workstreams</th>
            <th>Deliverables</th>
            <th>Open Reminders</th>
            <th>Generated By</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {snapshots.map((item) => (
            <tr key={item.id}>
              <td>
                <strong>{item.snapshot_title}</strong>
                <div className="small-note">{shortText(item.summary_text, 180)}</div>
              </td>
              <td><StatusBadge status={item.health_status} /></td>
              <td>{item.total_workstreams}</td>
              <td>{item.total_deliverables}</td>
              <td>{item.open_reminders}</td>
              <td>{item.generated_by ?? "-"}</td>
              <td>{formatDateTime(item.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Mvp16OperationsPanel() {
  const queryClient = useQueryClient();

  const [userForm, setUserForm] = useState({
    username: "",
    display_name: "",
    email: "",
    role: "Delivery Owner",
  });

  const [auditForm, setAuditForm] = useState({
    event_type: "management_note",
    event_category: "Management Note",
    description: "",
    severity: "Info",
  });

  const dashboardQuery = useQuery({
    queryKey: ["operations-dashboard"],
    queryFn: getOperationsDashboard,
    retry: 1,
  });

  const usersQuery = useQuery({
    queryKey: ["operations-users"],
    queryFn: getAppUsers,
    retry: 1,
  });

  const rolesQuery = useQuery({
    queryKey: ["operations-roles"],
    queryFn: getRoles,
    retry: 1,
  });

  const notificationsQuery = useQuery({
    queryKey: ["operations-notifications"],
    queryFn: getOperationNotifications,
    retry: 1,
  });

  const auditEventsQuery = useQuery({
    queryKey: ["operations-audit-events"],
    queryFn: getAuditEvents,
    retry: 1,
  });

  const snapshotsQuery = useQuery({
    queryKey: ["operations-executive-snapshots"],
    queryFn: getExecutiveSnapshots,
    retry: 1,
  });

  const bootstrapUserMutation = useMutation({
    mutationFn: bootstrapCurrentUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["operations-users"] });
      queryClient.invalidateQueries({ queryKey: ["operations-audit-events"] });
      queryClient.invalidateQueries({ queryKey: ["operations-dashboard"] });
    },
  });

  const createUserMutation = useMutation({
    mutationFn: createAppUser,
    onSuccess: () => {
      setUserForm({
        username: "",
        display_name: "",
        email: "",
        role: "Delivery Owner",
      });
      queryClient.invalidateQueries({ queryKey: ["operations-users"] });
      queryClient.invalidateQueries({ queryKey: ["operations-audit-events"] });
      queryClient.invalidateQueries({ queryKey: ["operations-dashboard"] });
    },
  });

  const createAuditMutation = useMutation({
    mutationFn: createAuditEvent,
    onSuccess: () => {
      setAuditForm({
        event_type: "management_note",
        event_category: "Management Note",
        description: "",
        severity: "Info",
      });
      queryClient.invalidateQueries({ queryKey: ["operations-audit-events"] });
      queryClient.invalidateQueries({ queryKey: ["operations-dashboard"] });
    },
  });

  const generateNotificationsMutation = useMutation({
    mutationFn: generateOperationNotifications,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["operations-notifications"] });
      queryClient.invalidateQueries({ queryKey: ["operations-audit-events"] });
      queryClient.invalidateQueries({ queryKey: ["operations-dashboard"] });
    },
  });

  const updateNotificationMutation = useMutation({
    mutationFn: updateOperationNotification,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["operations-notifications"] });
      queryClient.invalidateQueries({ queryKey: ["operations-audit-events"] });
      queryClient.invalidateQueries({ queryKey: ["operations-dashboard"] });
    },
  });

  const createSnapshotMutation = useMutation({
    mutationFn: createExecutiveSnapshot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["operations-executive-snapshots"] });
      queryClient.invalidateQueries({ queryKey: ["operations-audit-events"] });
      queryClient.invalidateQueries({ queryKey: ["operations-dashboard"] });
    },
  });

  const users = usersQuery.data ?? [];
  const roles = rolesQuery.data ?? [];
  const notifications = notificationsQuery.data ?? [];
  const auditEvents = auditEventsQuery.data ?? [];
  const snapshots = snapshotsQuery.data ?? [];
  const dashboard = dashboardQuery.data;

  const executiveSummary = dashboard?.executive_summary;

  const availableRoleNames = useMemo(() => {
    if (roles.length === 0) {
      return [
        "Engagement Lead",
        "Delivery Owner",
        "Reviewer / Approver",
        "Data Gathering Owner",
        "Automation / AI Advisor",
      ];
    }

    return roles.map((item) => item.role);
  }, [roles]);

  function handleCreateUser() {
    if (!userForm.username.trim() || !userForm.display_name.trim()) {
      return;
    }

    createUserMutation.mutate({
      username: userForm.username.trim(),
      display_name: userForm.display_name.trim(),
      email: userForm.email.trim() || null,
      role: userForm.role,
      is_active: true,
    });
  }

  function handleCreateAuditEvent() {
    if (!auditForm.description.trim()) {
      return;
    }

    createAuditMutation.mutate({
      event_type: auditForm.event_type.trim() || "management_note",
      event_category: auditForm.event_category.trim() || "Management Note",
      description: auditForm.description.trim(),
      severity: auditForm.severity,
      details: {
        source: "MVP16 operations dashboard",
      },
    });
  }

  const isAnyLoading =
    dashboardQuery.isLoading ||
    usersQuery.isLoading ||
    rolesQuery.isLoading ||
    notificationsQuery.isLoading ||
    auditEventsQuery.isLoading ||
    snapshotsQuery.isLoading;

  const hasAnyError =
    dashboardQuery.isError ||
    usersQuery.isError ||
    rolesQuery.isError ||
    notificationsQuery.isError ||
    auditEventsQuery.isError ||
    snapshotsQuery.isError;

  return (
    <section id="operations-dashboard" className="content-section">
      <div className="section-header">
        <div>
          <h2>Operations, Governance, Notifications, and Executive Reporting</h2>
          <p>
            Combined MVP 16 dashboard for user governance, roles, audit events,
            notifications, executive health, and snapshots.
          </p>
        </div>
        <StatusBadge status={hasAnyError ? "Operations API Error" : isAnyLoading ? "Loading" : "Operations Ready"} />
      </div>

      {hasAnyError ? (
        <div className="dictation-message">
          Could not load one or more Operations APIs. If API_AUTH_ENABLED=true, make sure you are logged in
          and the browser has a valid session token.
        </div>
      ) : null}

      <div className="report-summary-grid">
        <div className="report-card">
          <span>Health Status</span>
          <strong>{executiveSummary?.health_status ?? "-"}</strong>
          <p>Executive cockpit health</p>
        </div>

        <div className="report-card">
          <span>Users</span>
          <strong>{dashboard?.users ?? users.length}</strong>
          <p>{dashboard?.active_users ?? users.filter((item) => item.is_active).length} active</p>
        </div>

        <div className="report-card">
          <span>Audit Events</span>
          <strong>{dashboard?.audit_events ?? auditEvents.length}</strong>
          <p>Governance history</p>
        </div>

        <div className="report-card">
          <span>Unread Notifications</span>
          <strong>{dashboard?.unread_notifications ?? notifications.filter((item) => item.status === "Unread").length}</strong>
          <p>{dashboard?.open_notifications ?? notifications.length} open notifications</p>
        </div>

        <div className="report-card">
          <span>Open Reminders</span>
          <strong>{executiveSummary?.counts.open_reminders ?? 0}</strong>
          <p>Management attention items</p>
        </div>

        <div className="report-card">
          <span>Review Actions</span>
          <strong>{executiveSummary?.counts.open_review_actions ?? 0}</strong>
          <p>Open review follow-ups</p>
        </div>

        <div className="report-card">
          <span>Recommendation Actions</span>
          <strong>{executiveSummary?.counts.open_recommendation_actions ?? 0}</strong>
          <p>Open AI/action follow-ups</p>
        </div>

        <div className="report-card">
          <span>Snapshots</span>
          <strong>{snapshots.length}</strong>
          <p>Executive snapshots saved</p>
        </div>
      </div>

      <div className="timesheet-card">
        <h3>Executive Summary</h3>
        <p>{executiveSummary?.summary_text ?? "Executive summary is loading."}</p>

        <div className="timesheet-grid">
          <div>
            <h4>Risks</h4>
            <ul className="compact-list">
              {(executiveSummary?.risks ?? []).map((risk) => (
                <li key={risk}>{risk}</li>
              ))}
            </ul>
          </div>

          <div>
            <h4>Recommended Management Actions</h4>
            <ul className="compact-list">
              {(executiveSummary?.recommended_management_actions ?? []).map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ul>
          </div>
        </div>

        <div className="button-row">
          <button
            className="primary-button"
            onClick={() => createSnapshotMutation.mutate()}
            disabled={createSnapshotMutation.isPending}
          >
            {createSnapshotMutation.isPending ? "Creating Snapshot..." : "Create Executive Snapshot"}
          </button>

          <button
            className="secondary-button"
            onClick={() => generateNotificationsMutation.mutate()}
            disabled={generateNotificationsMutation.isPending}
          >
            {generateNotificationsMutation.isPending ? "Generating..." : "Generate Notifications from Reminders"}
          </button>

          <button
            className="secondary-button"
            onClick={() => bootstrapUserMutation.mutate()}
            disabled={bootstrapUserMutation.isPending}
          >
            {bootstrapUserMutation.isPending ? "Bootstrapping..." : "Bootstrap Current User"}
          </button>
        </div>
      </div>

      <div className="timesheet-grid">
        <div className="timesheet-card">
          <h3>Create Application User</h3>
          <p>Add a local user profile for role/governance tracking.</p>

          <div className="timesheet-form-grid">
            <label>
              Username
              <input
                value={userForm.username}
                onChange={(event) => setUserForm((current) => ({ ...current, username: event.target.value }))}
                placeholder="example: delivery.owner"
              />
            </label>

            <label>
              Display Name
              <input
                value={userForm.display_name}
                onChange={(event) => setUserForm((current) => ({ ...current, display_name: event.target.value }))}
                placeholder="example: Delivery Owner"
              />
            </label>

            <label>
              Email
              <input
                value={userForm.email}
                onChange={(event) => setUserForm((current) => ({ ...current, email: event.target.value }))}
                placeholder="optional"
              />
            </label>

            <label>
              Role
              <select
                value={userForm.role}
                onChange={(event) => setUserForm((current) => ({ ...current, role: event.target.value }))}
              >
                {availableRoleNames.map((roleName) => (
                  <option key={roleName} value={roleName}>{roleName}</option>
                ))}
              </select>
            </label>
          </div>

          <button
            className="primary-button"
            onClick={handleCreateUser}
            disabled={createUserMutation.isPending}
          >
            {createUserMutation.isPending ? "Creating..." : "Create User"}
          </button>

          {createUserMutation.isError ? (
            <div className="dictation-message">
              {createUserMutation.error instanceof Error ? createUserMutation.error.message : "Could not create user."}
            </div>
          ) : null}
        </div>

        <div className="timesheet-card">
          <h3>Create Audit / Management Note</h3>
          <p>Capture an explicit activity event or management note.</p>

          <div className="timesheet-form-grid">
            <label>
              Event Type
              <input
                value={auditForm.event_type}
                onChange={(event) => setAuditForm((current) => ({ ...current, event_type: event.target.value }))}
              />
            </label>

            <label>
              Category
              <input
                value={auditForm.event_category}
                onChange={(event) => setAuditForm((current) => ({ ...current, event_category: event.target.value }))}
              />
            </label>

            <label>
              Severity
              <select
                value={auditForm.severity}
                onChange={(event) => setAuditForm((current) => ({ ...current, severity: event.target.value }))}
              >
                <option value="Info">Info</option>
                <option value="Low">Low</option>
                <option value="Medium">Medium</option>
                <option value="High">High</option>
              </select>
            </label>
          </div>

          <label>
            Description
            <textarea
              value={auditForm.description}
              onChange={(event) => setAuditForm((current) => ({ ...current, description: event.target.value }))}
              placeholder="Enter management note or activity description..."
              rows={5}
            />
          </label>

          <button
            className="primary-button"
            onClick={handleCreateAuditEvent}
            disabled={createAuditMutation.isPending}
          >
            {createAuditMutation.isPending ? "Saving..." : "Create Audit Event"}
          </button>
        </div>
      </div>

      <div className="timesheet-card">
        <h3>Users</h3>
        <UsersTable users={users} />
      </div>

      <div className="timesheet-card">
        <h3>Roles and Permission Metadata</h3>
        <RolesTable roles={roles} />
      </div>

      <div className="timesheet-card">
        <h3>Notifications</h3>
        <NotificationsTable
          notifications={notifications}
          isUpdating={updateNotificationMutation.isPending}
          onMarkRead={(id) => updateNotificationMutation.mutate({ notification_id: id, status: "Read" })}
          onDismiss={(id) => updateNotificationMutation.mutate({ notification_id: id, status: "Dismissed" })}
        />
      </div>

      <div className="timesheet-card">
        <h3>Audit and Activity History</h3>
        <AuditEventsTable auditEvents={auditEvents} />
      </div>

      <div className="timesheet-card">
        <h3>Executive Snapshots</h3>
        <ExecutiveSnapshotsTable snapshots={snapshots} />
      </div>
    </section>
  );
}