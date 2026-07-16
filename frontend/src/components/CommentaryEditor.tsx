import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import { getDashboardCommentary, upsertDashboardCommentary } from "../api/dashboard";
import type {
  DashboardCommentaryContext,
  DashboardCommentaryRecord,
} from "../api/dashboard";

type CommentaryEditorProps = DashboardCommentaryContext & {
  disabled?: boolean;
};

type ActiveCommentaryEditor = {
  signature: string;
  saveAndClose: () => Promise<boolean>;
};

let activeCommentaryEditor: ActiveCommentaryEditor | null = null;

function normalizedContext(input: DashboardCommentaryContext): Required<DashboardCommentaryContext> {
  return {
    project_id: input.project_id,
    dashboard_area: input.dashboard_area,
    tab_name: input.tab_name,
    sub_tab_name: input.sub_tab_name ?? null,
    section_key: input.section_key,
    chart_key: input.chart_key ?? null,
    scope_filter: input.scope_filter ?? "all",
    ticket_type_filter: input.ticket_type_filter ?? "all",
    functional_track_ams_owner: input.functional_track_ams_owner ?? "all",
  };
}

function contextSignature(context: Required<DashboardCommentaryContext>): string {
  return [
    context.project_id,
    context.dashboard_area,
    context.tab_name,
    context.sub_tab_name ?? "",
    context.section_key,
    context.chart_key ?? "",
    context.scope_filter,
    context.ticket_type_filter,
    context.functional_track_ams_owner,
  ].join("|");
}

function formatTimestamp(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function emptyHtml(value: string | null | undefined): boolean {
  if (!value) {
    return true;
  }
  const withoutTags = value.replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ").trim();
  return withoutTags.length === 0;
}

export default function CommentaryEditor(props: CommentaryEditorProps) {
  const context = useMemo(
    () => normalizedContext(props),
    [
      props.project_id,
      props.dashboard_area,
      props.tab_name,
      props.sub_tab_name,
      props.section_key,
      props.chart_key,
      props.scope_filter,
      props.ticket_type_filter,
      props.functional_track_ams_owner,
    ]
  );
  const signature = useMemo(() => contextSignature(context), [context]);
  const [isEditing, setIsEditing] = useState(false);
  const [commentary, setCommentary] = useState<DashboardCommentaryRecord | null>(null);
  const [draftHtml, setDraftHtml] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const editorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setMessage(null);
    void getDashboardCommentary(context)
      .then((response) => {
        if (cancelled) {
          return;
        }
        const nextCommentary = response.commentary;
        setCommentary(nextCommentary);
        setDraftHtml(nextCommentary?.commentary_html ?? "");
        if (editorRef.current) {
          editorRef.current.innerHTML = nextCommentary?.commentary_html ?? "";
        }
        setStatus("idle");
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        const text = error instanceof Error ? error.message : "Unable to load commentary.";
        setMessage(text);
        setStatus("error");
      });

    return () => {
      cancelled = true;
      if (activeCommentaryEditor?.signature === signature) {
        activeCommentaryEditor = null;
      }
    };
  }, [context, signature]);

  const executeCommand = useCallback((command: string) => {
    editorRef.current?.focus();
    document.execCommand(command, false);
  }, []);

  const resetDraft = useCallback(() => {
    const html = commentary?.commentary_html ?? "";
    setDraftHtml(html);
    if (editorRef.current) {
      editorRef.current.innerHTML = html;
    }
    setIsEditing(false);
    setStatus("idle");
    setMessage(null);
    if (activeCommentaryEditor?.signature === signature) {
      activeCommentaryEditor = null;
    }
  }, [commentary, signature]);

  const saveDraft = useCallback(async () => {
    const html = editorRef.current?.innerHTML ?? draftHtml;
    const text = editorRef.current?.innerText ?? "";
    setStatus("saving");
    setMessage(null);
    try {
      const response = await upsertDashboardCommentary({
        ...context,
        commentary_html: emptyHtml(html) ? null : html,
        commentary_text: text.trim() || null,
      });
      setCommentary(response.commentary);
      setDraftHtml(response.commentary?.commentary_html ?? "");
      if (editorRef.current) {
        editorRef.current.innerHTML = response.commentary?.commentary_html ?? "";
      }
      setStatus("saved");
      setMessage("Commentary saved.");
      setIsEditing(false);
      if (activeCommentaryEditor?.signature === signature) {
        activeCommentaryEditor = null;
      }
      return true;
    } catch (error: unknown) {
      const textMessage = error instanceof Error ? error.message : "Unable to save commentary.";
      setMessage(textMessage);
      setStatus("error");
      return false;
    }
  }, [context, draftHtml, signature]);

  const clearCommentary = useCallback(async () => {
    setDraftHtml("");
    if (editorRef.current) {
      editorRef.current.innerHTML = "";
    }
    return saveDraft();
  }, [saveDraft]);

  const beginEditing = useCallback(async () => {
    if (props.disabled || status === "loading" || status === "saving") {
      return;
    }
    if (activeCommentaryEditor && activeCommentaryEditor.signature !== signature) {
      const saved = await activeCommentaryEditor.saveAndClose();
      if (!saved) {
        setMessage("Another commentary could not be auto-saved. Please save it first.");
        setStatus("error");
        return;
      }
    }
    activeCommentaryEditor = {
      signature,
      saveAndClose: saveDraft,
    };
    setIsEditing(true);
    setMessage(null);
    window.setTimeout(() => editorRef.current?.focus(), 0);
  }, [props.disabled, saveDraft, signature, status]);

  const handleEditorKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.ctrlKey && event.key === "Enter") {
        event.preventDefault();
        void saveDraft();
      }
      if (event.key === "Escape") {
        event.preventDefault();
        resetDraft();
      }
    },
    [resetDraft, saveDraft]
  );

  const savedAt = formatTimestamp(commentary?.updated_at);
  const hasCommentary = !emptyHtml(commentary?.commentary_html);

  return (
    <section className="commentary-box" aria-label="Commentary / Inferences">
      <div className="commentary-box-header">
        <div>
          <p className="label">Commentary / Inferences</p>
          {savedAt ? <p className="muted-text">Last saved {savedAt}</p> : null}
        </div>
        {isEditing ? (
          <div className="commentary-icon-actions">
            <button
              aria-label="Clear commentary"
              className="commentary-icon-button"
              type="button"
              disabled={status === "saving"}
              onClick={() => void clearCommentary()}
            >
              x
            </button>
            <button
              aria-label="Save commentary"
              className="commentary-icon-button primary"
              type="button"
              disabled={status === "saving"}
              onClick={() => void saveDraft()}
            >
              ✓
            </button>
          </div>
        ) : (
          <button
            aria-label="Edit commentary"
            className="commentary-icon-button"
            type="button"
            disabled={props.disabled || status === "loading"}
            onClick={() => void beginEditing()}
          >
            ✎
          </button>
        )}
      </div>

      {!isEditing && hasCommentary ? (
        <div
          className="commentary-preview"
          dangerouslySetInnerHTML={{ __html: commentary?.commentary_html ?? "" }}
        />
      ) : null}
      {!isEditing && !hasCommentary && status !== "loading" ? (
        <p className="muted-text commentary-empty">No commentary added yet.</p>
      ) : null}

      {isEditing ? (
        <div className="commentary-editor-panel">
          <div className="commentary-toolbar" aria-label="Rich text toolbar">
            <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => executeCommand("bold")}>
              B
            </button>
            <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => executeCommand("italic")}>
              I
            </button>
            <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => executeCommand("underline")}>
              U
            </button>
            <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => executeCommand("insertUnorderedList")}>
              Bullets
            </button>
            <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => executeCommand("insertOrderedList")}>
              Numbered
            </button>
            <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => executeCommand("removeFormat")}>
              Remove format
            </button>
          </div>
          <div
            className="commentary-editor"
            contentEditable
            dangerouslySetInnerHTML={{ __html: draftHtml }}
            ref={editorRef}
            role="textbox"
            suppressContentEditableWarning
            onKeyDown={handleEditorKeyDown}
          />
        </div>
      ) : null}
      {status === "loading" ? <p className="muted-text commentary-status">Loading commentary...</p> : null}
      {message ? (
        <p className={status === "error" ? "error-text commentary-status" : "muted-text commentary-status"}>
          {message}
        </p>
      ) : null}
    </section>
  );
}
