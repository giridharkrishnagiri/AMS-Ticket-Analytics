import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  clearStoredSession,
  getAuthStatus,
  getStoredSession,
  isLoginRequired,
  login,
  storeSession,
  type StoredSession,
} from "./api";

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "-";
  }

  return value.replace("T", " ").slice(0, 19);
}

function StatusBadge({ status }: { status: string }) {
  return <span className="status-badge">{status}</span>;
}

export function Mvp15AuthPanel({
  onSessionChange,
}: {
  onSessionChange?: (session: StoredSession | null) => void;
}) {
  const queryClient = useQueryClient();

  const [session, setSession] = useState<StoredSession | null>(() => getStoredSession());
  const [username, setUsername] = useState("giridhar");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");

  const authStatusQuery = useQuery({
    queryKey: ["auth-status", session?.access_token ?? "no-session"],
    queryFn: getAuthStatus,
    retry: 1,
  });

  useEffect(() => {
    onSessionChange?.(session);
  }, [onSessionChange, session]);

  async function handleLogin() {
    setMessage("");

    if (!username.trim()) {
      setMessage("Username is required.");
      return;
    }

    if (!password.trim()) {
      setMessage("Password is required.");
      return;
    }

    try {
      const response = await login({
        username: username.trim(),
        password,
      });

      const storedSession = storeSession(response);
      setSession(storedSession);
      setPassword("");
      setMessage("Login successful.");

      queryClient.invalidateQueries();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Login failed.");
    }
  }

  function handleLogout() {
    clearStoredSession();
    setSession(null);
    setMessage("Logged out from local session.");

    queryClient.invalidateQueries();
  }

  const loginRequired = isLoginRequired();

  return (
    <section id="auth-session" className="content-section">
      <div className="section-header">
        <div>
          <h2>Login and Session</h2>
          <p>
            Sign in to create a local session token. The token is stored in browser localStorage
            and sent automatically on protected backend API calls.
          </p>
        </div>
        <StatusBadge status={session ? "Session Available" : loginRequired ? "Login Required" : "Login Optional"} />
      </div>

      <div className="report-summary-grid">
        <div className="report-card">
          <span>Login Mode</span>
          <strong>{loginRequired ? "Required" : "Optional"}</strong>
          <p>Controlled by VITE_APP_LOGIN_REQUIRED</p>
        </div>

        <div className="report-card">
          <span>Local Session</span>
          <strong>{session ? "Active" : "Not Active"}</strong>
          <p>Stored in browser localStorage</p>
        </div>

        <div className="report-card">
          <span>Backend Auth Status</span>
          <strong>
            {authStatusQuery.isLoading
              ? "Checking"
              : authStatusQuery.isError
                ? "Error"
                : authStatusQuery.data?.auth_type ?? "-"}
          </strong>
          <p>Reads /api/auth/status</p>
        </div>

        <div className="report-card">
          <span>Session User</span>
          <strong>{session?.display_name ?? "-"}</strong>
          <p>{session?.username ?? "No local session"}</p>
        </div>
      </div>

      <div className="timesheet-grid">
        <div className="timesheet-card">
          <h3>Login</h3>
          <p>
            Use the username and password configured in backend <code>.env</code>.
          </p>

          <div className="timesheet-form-grid">
            <label>
              Username
              <input value={username} onChange={(event) => setUsername(event.target.value)} />
            </label>

            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
          </div>

          <div className="button-row">
            <button className="primary-button" onClick={handleLogin}>
              Login
            </button>

            <button className="secondary-button" onClick={handleLogout}>
              Logout
            </button>
          </div>

          {message ? <div className="dictation-message">{message}</div> : null}
        </div>

        <div className="timesheet-card">
          <h3>Session Details</h3>

          {session ? (
            <div className="table-card wide-table">
              <table>
                <tbody>
                  <tr>
                    <td><strong>Display Name</strong></td>
                    <td>{session.display_name}</td>
                  </tr>
                  <tr>
                    <td><strong>Username</strong></td>
                    <td>{session.username}</td>
                  </tr>
                  <tr>
                    <td><strong>Token Type</strong></td>
                    <td>{session.token_type}</td>
                  </tr>
                  <tr>
                    <td><strong>Login Timestamp</strong></td>
                    <td>{formatDateTime(session.login_timestamp)}</td>
                  </tr>
                  <tr>
                    <td><strong>Session Duration</strong></td>
                    <td>{session.expires_in_minutes} minutes</td>
                  </tr>
                </tbody>
              </table>
            </div>
          ) : (
            <div className="selected-context">
              No local session is stored. Login is optional until VITE_APP_LOGIN_REQUIRED is set to true.
            </div>
          )}

          <div className="selected-context">
            Backend auth status:{" "}
            {authStatusQuery.isError
              ? "Could not load auth status"
              : authStatusQuery.isLoading
                ? "Loading..."
                : `${authStatusQuery.data?.authenticated ? "Authenticated" : "Not authenticated"} (${authStatusQuery.data?.auth_type})`}
          </div>
        </div>
      </div>
    </section>
  );
}