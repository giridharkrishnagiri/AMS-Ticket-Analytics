import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import "./mvp18Workspace.css";

import {
  createAnalysis,
  createDataCollection,
  createEvidence,
  createFinding,
  createQuestion,
  deleteAnalysis,
  deleteDataCollection,
  deleteEvidence,
  deleteFinding,
  deleteQuestion,
  deleteWorkspaceFile,
  generateWorkspaceRecommendation,
  getWorkspaceRecords,
  refineWorkspaceText,
  updateAnalysis,
  updateDataCollection,
  updateEvidence,
  updateFinding,
  updateQuestion,
  uploadWorkspaceFile,
  type WorkspaceAnalysis,
  type WorkspaceDataCollection,
  type WorkspaceEvidence,
  type WorkspaceFinding,
  type WorkspaceFullRecords,
  type WorkspaceQuestion,
  type WorkspaceRecommendation,
  type WorkspaceScopeType,
} from "./mvp18WorkspaceApi";

type WorkspaceTab = "data" | "questions" | "findings" | "analysis" | "evidence" | "recommendations";
type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: { results: ArrayLike<{ 0: { transcript: string } }> }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

declare global {
  interface Window {
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    SpeechRecognition?: new () => SpeechRecognitionLike;
  }
}

const EMPTY_RECORDS: WorkspaceFullRecords = {
  data_collections: [],
  questions: [],
  findings: [],
  analysis: [],
  evidence: [],
  files: [],
  recommendations: [],
};

const TAB_LABELS: Array<{ key: WorkspaceTab; label: string }> = [
  { key: "data", label: "Data Collection" },
  { key: "questions", label: "Questions & Responses" },
  { key: "findings", label: "Findings" },
  { key: "analysis", label: "Analysis" },
  { key: "evidence", label: "Evidence & Files" },
  { key: "recommendations", label: "Recommendations" },
];

function getSessionDisplayName(): string {
  const raw = window.localStorage.getItem("asm_engagement_cockpit_session");
  if (!raw) return "";

  try {
    const session = JSON.parse(raw) as { display_name?: string };
    return session.display_name || "";
  } catch {
    return "";
  }
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  return value.replace("T", " ").slice(0, 19);
}

function truncate(value: string | null | undefined, maxLength = 140): string {
  if (!value) return "-";
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength)}...`;
}

function confirmDelete(label: string): boolean {
  return window.confirm(`Are you sure you want to delete this ${label}?\n\nThis action cannot be undone.`);
}

function useDictation(onTranscript: (text: string) => void) {
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [message, setMessage] = useState("");

  function start() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      setMessage("Mic dictation is not supported by this browser. Use Chrome or Edge.");
      return;
    }

    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US";
    recognition.onresult = (event) => {
      const parts: string[] = [];
      for (let index = 0; index < event.results.length; index += 1) {
        parts.push(event.results[index][0].transcript);
      }
      onTranscript(parts.join(" ").trim());
    };
    recognition.onend = () => setIsListening(false);

    recognitionRef.current = recognition;
    recognition.start();
    setMessage("");
    setIsListening(true);
  }

  function stop() {
    recognitionRef.current?.stop();
    setIsListening(false);
  }

  return { isListening, message, start, stop };
}

function DictationRefinementBox({
  label,
  rawText,
  refinedText,
  onRawTextChange,
  onRefinedTextChange,
  onReplace,
  onAppend,
  context,
}: {
  label: string;
  rawText: string;
  refinedText: string;
  onRawTextChange: (value: string) => void;
  onRefinedTextChange: (value: string) => void;
  onReplace: () => void;
  onAppend: () => void;
  context: string;
}) {
  const dictation = useDictation((text) => {
    onRawTextChange(rawText ? `${rawText}\n${text}` : text);
  });

  const refineMutation = useMutation({
    mutationFn: refineWorkspaceText,
    onSuccess: (response) => {
      onRefinedTextChange(response.refined_text);
    },
  });

  return (
    <div className="mvp18-workspace-dictation-box">
      <div className="mvp18-workspace-field-header">
        <strong>{label}</strong>
        <div className="mvp18-workspace-button-row compact">
          <button type="button" className="mvp18-button-secondary" onClick={dictation.start} disabled={dictation.isListening}>
            🎙️ Start Mic
          </button>
          <button type="button" className="mvp18-button-secondary" onClick={dictation.stop} disabled={!dictation.isListening}>
            Stop
          </button>
          <button
            type="button"
            className="mvp18-button-primary"
            onClick={() => refineMutation.mutate({ text: rawText, context })}
            disabled={!rawText.trim() || refineMutation.isPending}
          >
            {refineMutation.isPending ? "Refining..." : "Refine with LLM"}
          </button>
        </div>
      </div>

      {dictation.message ? <div className="mvp18-workspace-message">{dictation.message}</div> : null}
      {dictation.isListening ? <div className="mvp18-workspace-listening">Listening. Speak now, then click Stop.</div> : null}
      {refineMutation.isError ? (
        <div className="mvp18-workspace-error">{refineMutation.error instanceof Error ? refineMutation.error.message : "Refinement failed."}</div>
      ) : null}

      <div className="mvp18-workspace-two-column">
        <label>
          Raw dictated / typed text
          <textarea value={rawText} onChange={(event) => onRawTextChange(event.target.value)} rows={8} />
        </label>
        <label>
          Refined LLM text
          <textarea value={refinedText} onChange={(event) => onRefinedTextChange(event.target.value)} rows={8} />
        </label>
      </div>

      <div className="mvp18-workspace-button-row">
        <button type="button" className="mvp18-button-secondary" onClick={onReplace} disabled={!refinedText.trim()}>
          Replace main text
        </button>
        <button type="button" className="mvp18-button-secondary" onClick={onAppend} disabled={!refinedText.trim()}>
          Append to main text
        </button>
      </div>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return <div className="mvp18-workspace-empty">{label}</div>;
}

function FileUploadInline({
  scopeType,
  scopeId,
  linkedEntityType,
  linkedEntityId,
  defaultCategory,
}: {
  scopeType: WorkspaceScopeType;
  scopeId: string;
  linkedEntityType?: string;
  linkedEntityId?: string;
  defaultCategory: string;
}) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [description, setDescription] = useState("");

  const uploadMutation = useMutation({
    mutationFn: uploadWorkspaceFile,
    onSuccess: () => {
      setFile(null);
      setDescription("");
      queryClient.invalidateQueries({ queryKey: ["mvp18-workspace-records", scopeType, scopeId] });
    },
  });

  return (
    <div className="mvp18-workspace-upload-inline">
      <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
      <input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="File description" />
      <button
        type="button"
        className="mvp18-button-secondary"
        disabled={!file || uploadMutation.isPending}
        onClick={() => {
          if (!file) return;
          uploadMutation.mutate({
            scopeType,
            scopeId,
            file,
            uploadCategory: defaultCategory,
            description,
            linkedEntityType,
            linkedEntityId,
            uploadedBy: getSessionDisplayName(),
          });
        }}
      >
        {uploadMutation.isPending ? "Uploading..." : "Upload File"}
      </button>
      {uploadMutation.isError ? (
        <span className="mvp18-workspace-error">{uploadMutation.error instanceof Error ? uploadMutation.error.message : "Upload failed."}</span>
      ) : null}
    </div>
  );
}

function DataCollectionTab({ scopeType, scopeId, records }: WorkspaceTabProps) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<WorkspaceDataCollection | null>(null);
  const [form, setForm] = useState({ topic: "", source: "", status: "Requested", expected_received_date: "", actual_received_date: "", data_quality: "", notes: "" });

  const reset = () => {
    setEditing(null);
    setForm({ topic: "", source: "", status: "Requested", expected_received_date: "", actual_received_date: "", data_quality: "", notes: "" });
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = { ...form, created_by: getSessionDisplayName(), updated_by: getSessionDisplayName() };
      if (editing) return updateDataCollection(editing.id, payload);
      return createDataCollection(scopeType, scopeId, payload);
    },
    onSuccess: () => {
      reset();
      queryClient.invalidateQueries({ queryKey: ["mvp18-workspace-records", scopeType, scopeId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDataCollection,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mvp18-workspace-records", scopeType, scopeId] }),
  });

  return (
    <div className="mvp18-workspace-tab-body">
      <div className="mvp18-workspace-editor-card">
        <h3>{editing ? "Edit Data Collection Item" : "Add Data Collection Item"}</h3>
        <div className="mvp18-workspace-form-grid">
          <label>Topic<input value={form.topic} onChange={(event) => setForm({ ...form, topic: event.target.value })} /></label>
          <label>Source<input value={form.source} onChange={(event) => setForm({ ...form, source: event.target.value })} /></label>
          <label>Status<input value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })} /></label>
          <label>Expected Date<input type="date" value={form.expected_received_date} onChange={(event) => setForm({ ...form, expected_received_date: event.target.value })} /></label>
          <label>Actual Date<input type="date" value={form.actual_received_date} onChange={(event) => setForm({ ...form, actual_received_date: event.target.value })} /></label>
          <label>Data Quality<input value={form.data_quality} onChange={(event) => setForm({ ...form, data_quality: event.target.value })} /></label>
        </div>
        <label>Notes<textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} rows={4} /></label>
        <div className="mvp18-workspace-button-row">
          <button className="mvp18-button-primary" onClick={() => saveMutation.mutate()} disabled={!form.topic.trim() || saveMutation.isPending}>{saveMutation.isPending ? "Saving..." : "Save Data Collection"}</button>
          {editing ? <button className="mvp18-button-secondary" onClick={reset}>Cancel Edit</button> : null}
        </div>
      </div>

      <WorkspaceTable headers={["Topic", "Source", "Status", "Expected", "Actual", "Quality", "Actions"]}>
        {records.data_collections.map((item) => (
          <tr key={item.id}>
            <td><strong>{item.topic}</strong><div className="mvp18-workspace-small">{truncate(item.notes)}</div></td>
            <td>{item.source || "-"}</td><td>{item.status}</td><td>{item.expected_received_date || "-"}</td><td>{item.actual_received_date || "-"}</td><td>{item.data_quality || "-"}</td>
            <td><RowActions onEdit={() => { setEditing(item); setForm({ topic: item.topic, source: item.source || "", status: item.status, expected_received_date: item.expected_received_date || "", actual_received_date: item.actual_received_date || "", data_quality: item.data_quality || "", notes: item.notes || "" }); }} onDelete={() => confirmDelete("data collection item") && deleteMutation.mutate(item.id)} /></td>
          </tr>
        ))}
      </WorkspaceTable>
      {records.data_collections.length === 0 ? <EmptyState label="No data collection items yet." /> : null}
    </div>
  );
}

function QuestionsTab({ scopeType, scopeId, records }: WorkspaceTabProps) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<WorkspaceQuestion | null>(null);
  const [form, setForm] = useState({ question_text: "", stakeholder_name: "", stakeholder_role: "", response_status: "Pending", expected_response_date: "", actual_response_date: "", response_details: "", follow_up_required: false });

  const reset = () => {
    setEditing(null);
    setForm({ question_text: "", stakeholder_name: "", stakeholder_role: "", response_status: "Pending", expected_response_date: "", actual_response_date: "", response_details: "", follow_up_required: false });
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = { ...form, created_by: getSessionDisplayName(), updated_by: getSessionDisplayName() };
      if (editing) return updateQuestion(editing.id, payload);
      return createQuestion(scopeType, scopeId, payload);
    },
    onSuccess: () => {
      reset();
      queryClient.invalidateQueries({ queryKey: ["mvp18-workspace-records", scopeType, scopeId] });
    },
  });

  const deleteMutation = useMutation({ mutationFn: deleteQuestion, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mvp18-workspace-records", scopeType, scopeId] }) });

  return (
    <div className="mvp18-workspace-tab-body">
      <div className="mvp18-workspace-editor-card">
        <h3>{editing ? "Edit Question / Response" : "Add Question / Response"}</h3>
        <label>Question<textarea value={form.question_text} onChange={(event) => setForm({ ...form, question_text: event.target.value })} rows={4} /></label>
        <div className="mvp18-workspace-form-grid">
          <label>Stakeholder<input value={form.stakeholder_name} onChange={(event) => setForm({ ...form, stakeholder_name: event.target.value })} /></label>
          <label>Role<input value={form.stakeholder_role} onChange={(event) => setForm({ ...form, stakeholder_role: event.target.value })} /></label>
          <label>Status<input value={form.response_status} onChange={(event) => setForm({ ...form, response_status: event.target.value })} /></label>
          <label>Expected Date<input type="date" value={form.expected_response_date} onChange={(event) => setForm({ ...form, expected_response_date: event.target.value })} /></label>
          <label>Actual Date<input type="date" value={form.actual_response_date} onChange={(event) => setForm({ ...form, actual_response_date: event.target.value })} /></label>
          <label className="mvp18-workspace-checkbox"><input type="checkbox" checked={form.follow_up_required} onChange={(event) => setForm({ ...form, follow_up_required: event.target.checked })} /> Follow-up required</label>
        </div>
        <label>Response Details<textarea value={form.response_details} onChange={(event) => setForm({ ...form, response_details: event.target.value })} rows={4} /></label>
        <div className="mvp18-workspace-button-row">
          <button className="mvp18-button-primary" onClick={() => saveMutation.mutate()} disabled={!form.question_text.trim() || saveMutation.isPending}>{saveMutation.isPending ? "Saving..." : "Save Question"}</button>
          {editing ? <button className="mvp18-button-secondary" onClick={reset}>Cancel Edit</button> : null}
        </div>
      </div>

      <WorkspaceTable headers={["Question", "Stakeholder", "Status", "Expected", "Actual", "Follow-up", "Actions"]}>
        {records.questions.map((item) => (
          <tr key={item.id}>
            <td><strong>{truncate(item.question_text, 90)}</strong><div className="mvp18-workspace-small">{truncate(item.response_details)}</div></td>
            <td>{item.stakeholder_name || "-"}<div className="mvp18-workspace-small">{item.stakeholder_role || ""}</div></td>
            <td>{item.response_status}</td><td>{item.expected_response_date || "-"}</td><td>{item.actual_response_date || "-"}</td><td>{item.follow_up_required ? "Yes" : "No"}</td>
            <td><RowActions onEdit={() => { setEditing(item); setForm({ question_text: item.question_text, stakeholder_name: item.stakeholder_name || "", stakeholder_role: item.stakeholder_role || "", response_status: item.response_status, expected_response_date: item.expected_response_date || "", actual_response_date: item.actual_response_date || "", response_details: item.response_details || "", follow_up_required: item.follow_up_required }); }} onDelete={() => confirmDelete("question") && deleteMutation.mutate(item.id)} /></td>
          </tr>
        ))}
      </WorkspaceTable>
      {records.questions.length === 0 ? <EmptyState label="No questions yet." /> : null}
    </div>
  );
}

function FindingsTab({ scopeType, scopeId, records }: WorkspaceTabProps) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<WorkspaceFinding | null>(null);
  const [form, setForm] = useState({ title: "", finding_type: "Observation", severity: "Medium", raw_text: "", refined_text: "", finding_text: "", business_impact: "", recommendation: "", status: "Draft", confidence_level: "Medium" });

  const reset = () => {
    setEditing(null);
    setForm({ title: "", finding_type: "Observation", severity: "Medium", raw_text: "", refined_text: "", finding_text: "", business_impact: "", recommendation: "", status: "Draft", confidence_level: "Medium" });
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = { ...form, created_by: getSessionDisplayName(), updated_by: getSessionDisplayName() };
      if (editing) return updateFinding(editing.id, payload);
      return createFinding(scopeType, scopeId, payload);
    },
    onSuccess: () => {
      reset();
      queryClient.invalidateQueries({ queryKey: ["mvp18-workspace-records", scopeType, scopeId] });
    },
  });
  const deleteMutation = useMutation({ mutationFn: deleteFinding, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mvp18-workspace-records", scopeType, scopeId] }) });

  return (
    <div className="mvp18-workspace-tab-body">
      <div className="mvp18-workspace-editor-card">
        <h3>{editing ? "Edit Finding" : "Add Finding"}</h3>
        <div className="mvp18-workspace-form-grid">
          <label>Title<input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
          <label>Type<input value={form.finding_type} onChange={(event) => setForm({ ...form, finding_type: event.target.value })} /></label>
          <label>Severity<input value={form.severity} onChange={(event) => setForm({ ...form, severity: event.target.value })} /></label>
          <label>Status<input value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })} /></label>
        </div>
        <DictationRefinementBox
          label="Finding Dictation and Refinement"
          rawText={form.raw_text}
          refinedText={form.refined_text}
          onRawTextChange={(value) => setForm({ ...form, raw_text: value, finding_text: form.finding_text || value })}
          onRefinedTextChange={(value) => setForm({ ...form, refined_text: value })}
          onReplace={() => setForm({ ...form, finding_text: form.refined_text })}
          onAppend={() => setForm({ ...form, finding_text: `${form.finding_text}\n${form.refined_text}`.trim() })}
          context={`${scopeType} workspace finding`}
        />
        <label>Main Finding Text<textarea value={form.finding_text} onChange={(event) => setForm({ ...form, finding_text: event.target.value })} rows={5} /></label>
        <label>Business Impact<textarea value={form.business_impact} onChange={(event) => setForm({ ...form, business_impact: event.target.value })} rows={3} /></label>
        <label>Recommendation<textarea value={form.recommendation} onChange={(event) => setForm({ ...form, recommendation: event.target.value })} rows={3} /></label>
        <div className="mvp18-workspace-button-row">
          <button className="mvp18-button-primary" onClick={() => saveMutation.mutate()} disabled={!form.title.trim() || !form.finding_text.trim() || saveMutation.isPending}>{saveMutation.isPending ? "Saving..." : "Save Finding"}</button>
          {editing ? <button className="mvp18-button-secondary" onClick={reset}>Cancel Edit</button> : null}
        </div>
      </div>

      <WorkspaceTable headers={["Finding", "Severity", "Status", "Impact", "Files", "Actions"]}>
        {records.findings.map((item) => (
          <tr key={item.id}>
            <td><strong>{item.title}</strong><div className="mvp18-workspace-small">{truncate(item.finding_text)}</div></td>
            <td>{item.severity || "-"}</td><td>{item.status}</td><td>{truncate(item.business_impact, 80)}</td>
            <td><FileUploadInline scopeType={scopeType} scopeId={scopeId} linkedEntityType="finding" linkedEntityId={item.id} defaultCategory="Finding" /></td>
            <td><RowActions onEdit={() => { setEditing(item); setForm({ title: item.title, finding_type: item.finding_type || "", severity: item.severity || "", raw_text: item.raw_text || "", refined_text: item.refined_text || "", finding_text: item.finding_text, business_impact: item.business_impact || "", recommendation: item.recommendation || "", status: item.status, confidence_level: item.confidence_level || "" }); }} onDelete={() => confirmDelete("finding") && deleteMutation.mutate(item.id)} /></td>
          </tr>
        ))}
      </WorkspaceTable>
      {records.findings.length === 0 ? <EmptyState label="No findings yet." /> : null}
    </div>
  );
}

function AnalysisTab({ scopeType, scopeId, records }: WorkspaceTabProps) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<WorkspaceAnalysis | null>(null);
  const [form, setForm] = useState({ analysis_title: "", analysis_type: "Detailed Analysis", raw_text: "", refined_text: "", analysis_text: "", methodology: "", assumptions: "", limitations: "", status: "Draft", confidence_level: "Medium" });

  const reset = () => {
    setEditing(null);
    setForm({ analysis_title: "", analysis_type: "Detailed Analysis", raw_text: "", refined_text: "", analysis_text: "", methodology: "", assumptions: "", limitations: "", status: "Draft", confidence_level: "Medium" });
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = { ...form, created_by: getSessionDisplayName(), updated_by: getSessionDisplayName() };
      if (editing) return updateAnalysis(editing.id, payload);
      return createAnalysis(scopeType, scopeId, payload);
    },
    onSuccess: () => {
      reset();
      queryClient.invalidateQueries({ queryKey: ["mvp18-workspace-records", scopeType, scopeId] });
    },
  });
  const deleteMutation = useMutation({ mutationFn: deleteAnalysis, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mvp18-workspace-records", scopeType, scopeId] }) });

  return (
    <div className="mvp18-workspace-tab-body">
      <div className="mvp18-workspace-editor-card">
        <h3>{editing ? "Edit Analysis" : "Add Analysis"}</h3>
        <div className="mvp18-workspace-form-grid">
          <label>Title<input value={form.analysis_title} onChange={(event) => setForm({ ...form, analysis_title: event.target.value })} /></label>
          <label>Type<input value={form.analysis_type} onChange={(event) => setForm({ ...form, analysis_type: event.target.value })} /></label>
          <label>Status<input value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })} /></label>
          <label>Confidence<input value={form.confidence_level} onChange={(event) => setForm({ ...form, confidence_level: event.target.value })} /></label>
        </div>
        <DictationRefinementBox
          label="Analysis Dictation and Refinement"
          rawText={form.raw_text}
          refinedText={form.refined_text}
          onRawTextChange={(value) => setForm({ ...form, raw_text: value, analysis_text: form.analysis_text || value })}
          onRefinedTextChange={(value) => setForm({ ...form, refined_text: value })}
          onReplace={() => setForm({ ...form, analysis_text: form.refined_text })}
          onAppend={() => setForm({ ...form, analysis_text: `${form.analysis_text}\n${form.refined_text}`.trim() })}
          context={`${scopeType} workspace analysis`}
        />
        <label>Main Analysis Text<textarea value={form.analysis_text} onChange={(event) => setForm({ ...form, analysis_text: event.target.value })} rows={7} /></label>
        <label>Methodology<textarea value={form.methodology} onChange={(event) => setForm({ ...form, methodology: event.target.value })} rows={3} /></label>
        <label>Assumptions<textarea value={form.assumptions} onChange={(event) => setForm({ ...form, assumptions: event.target.value })} rows={3} /></label>
        <div className="mvp18-workspace-button-row">
          <button className="mvp18-button-primary" onClick={() => saveMutation.mutate()} disabled={!form.analysis_title.trim() || !form.analysis_text.trim() || saveMutation.isPending}>{saveMutation.isPending ? "Saving..." : "Save Analysis"}</button>
          {editing ? <button className="mvp18-button-secondary" onClick={reset}>Cancel Edit</button> : null}
        </div>
      </div>

      <WorkspaceTable headers={["Analysis", "Type", "Status", "Confidence", "Files", "Actions"]}>
        {records.analysis.map((item) => (
          <tr key={item.id}>
            <td><strong>{item.analysis_title}</strong><div className="mvp18-workspace-small">{truncate(item.analysis_text)}</div></td>
            <td>{item.analysis_type || "-"}</td><td>{item.status}</td><td>{item.confidence_level || "-"}</td>
            <td><FileUploadInline scopeType={scopeType} scopeId={scopeId} linkedEntityType="analysis" linkedEntityId={item.id} defaultCategory="Analysis" /></td>
            <td><RowActions onEdit={() => { setEditing(item); setForm({ analysis_title: item.analysis_title, analysis_type: item.analysis_type || "", raw_text: item.raw_text || "", refined_text: item.refined_text || "", analysis_text: item.analysis_text, methodology: item.methodology || "", assumptions: item.assumptions || "", limitations: item.limitations || "", status: item.status, confidence_level: item.confidence_level || "" }); }} onDelete={() => confirmDelete("analysis") && deleteMutation.mutate(item.id)} /></td>
          </tr>
        ))}
      </WorkspaceTable>
      {records.analysis.length === 0 ? <EmptyState label="No analysis yet." /> : null}
    </div>
  );
}

function EvidenceTab({ scopeType, scopeId, records }: WorkspaceTabProps) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<WorkspaceEvidence | null>(null);
  const [form, setForm] = useState({ title: "", description: "", evidence_type: "Document", source_name: "", source_reference: "", evidence_date: "", confidence_level: "Medium", is_primary_evidence: false });

  const reset = () => {
    setEditing(null);
    setForm({ title: "", description: "", evidence_type: "Document", source_name: "", source_reference: "", evidence_date: "", confidence_level: "Medium", is_primary_evidence: false });
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = { ...form, created_by: getSessionDisplayName(), updated_by: getSessionDisplayName() };
      if (editing) return updateEvidence(editing.id, payload);
      return createEvidence(scopeType, scopeId, payload);
    },
    onSuccess: () => {
      reset();
      queryClient.invalidateQueries({ queryKey: ["mvp18-workspace-records", scopeType, scopeId] });
    },
  });
  const deleteMutation = useMutation({ mutationFn: deleteEvidence, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mvp18-workspace-records", scopeType, scopeId] }) });
  const deleteFileMutation = useMutation({ mutationFn: deleteWorkspaceFile, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mvp18-workspace-records", scopeType, scopeId] }) });

  return (
    <div className="mvp18-workspace-tab-body">
      <div className="mvp18-workspace-editor-card">
        <h3>{editing ? "Edit Evidence" : "Add Evidence"}</h3>
        <div className="mvp18-workspace-form-grid">
          <label>Title<input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
          <label>Type<input value={form.evidence_type} onChange={(event) => setForm({ ...form, evidence_type: event.target.value })} /></label>
          <label>Source<input value={form.source_name} onChange={(event) => setForm({ ...form, source_name: event.target.value })} /></label>
          <label>Evidence Date<input type="date" value={form.evidence_date} onChange={(event) => setForm({ ...form, evidence_date: event.target.value })} /></label>
        </div>
        <label>Description<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} rows={4} /></label>
        <div className="mvp18-workspace-button-row">
          <button className="mvp18-button-primary" onClick={() => saveMutation.mutate()} disabled={!form.title.trim() || saveMutation.isPending}>{saveMutation.isPending ? "Saving..." : "Save Evidence"}</button>
          {editing ? <button className="mvp18-button-secondary" onClick={reset}>Cancel Edit</button> : null}
        </div>
      </div>

      <div className="mvp18-workspace-editor-card">
        <h3>Upload Direct Workspace File</h3>
        <FileUploadInline scopeType={scopeType} scopeId={scopeId} defaultCategory="Workspace" />
      </div>

      <WorkspaceTable headers={["Evidence", "Type", "Source", "Date", "Files", "Actions"]}>
        {records.evidence.map((item) => (
          <tr key={item.id}>
            <td><strong>{item.title}</strong><div className="mvp18-workspace-small">{truncate(item.description)}</div></td>
            <td>{item.evidence_type}</td><td>{item.source_name || "-"}</td><td>{item.evidence_date || "-"}</td>
            <td><FileUploadInline scopeType={scopeType} scopeId={scopeId} linkedEntityType="evidence" linkedEntityId={item.id} defaultCategory="Evidence" /></td>
            <td><RowActions onEdit={() => { setEditing(item); setForm({ title: item.title, description: item.description || "", evidence_type: item.evidence_type, source_name: item.source_name || "", source_reference: item.source_reference || "", evidence_date: item.evidence_date || "", confidence_level: item.confidence_level || "", is_primary_evidence: item.is_primary_evidence }); }} onDelete={() => confirmDelete("evidence") && deleteMutation.mutate(item.id)} /></td>
          </tr>
        ))}
      </WorkspaceTable>
      {records.evidence.length === 0 ? <EmptyState label="No evidence yet." /> : null}

      <h3>Uploaded Files</h3>
      <WorkspaceTable headers={["File", "Category", "Linked To", "Size", "Uploaded", "Actions"]}>
        {records.files.map((item) => (
          <tr key={item.id}>
            <td><strong>{item.original_filename}</strong><div className="mvp18-workspace-small">{truncate(item.description)}</div></td>
            <td>{item.upload_category}</td>
            <td>{item.linked_entity_type || "Workspace"}</td>
            <td>{item.file_size_bytes ? `${Math.round(item.file_size_bytes / 1024)} KB` : "-"}</td>
            <td>{formatDateTime(item.uploaded_at)}</td>
            <td><button className="mvp18-button-danger" onClick={() => confirmDelete("file") && deleteFileMutation.mutate(item.id)}>Delete</button></td>
          </tr>
        ))}
      </WorkspaceTable>
      {records.files.length === 0 ? <EmptyState label="No files uploaded yet." /> : null}
    </div>
  );
}

function RecommendationsTab({ scopeType, scopeId, records }: WorkspaceTabProps) {
  const queryClient = useQueryClient();
  const [focusArea, setFocusArea] = useState("Data gaps, questions, findings, risks, next steps");
  const generateMutation = useMutation({
    mutationFn: generateWorkspaceRecommendation,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mvp18-workspace-records", scopeType, scopeId] }),
  });

  return (
    <div className="mvp18-workspace-tab-body">
      <div className="mvp18-workspace-editor-card">
        <h3>Generate Contextual LLM Recommendation</h3>
        <p>
          This reads the task/sub-task description, data collections, questions and responses, findings, analysis, evidence metadata, uploaded file metadata, reminders, and existing recommendations.
        </p>
        <label>Focus Area<input value={focusArea} onChange={(event) => setFocusArea(event.target.value)} /></label>
        <button
          className="mvp18-button-primary"
          onClick={() => generateMutation.mutate({ scopeType, scopeId, focusArea, createdBy: getSessionDisplayName() })}
          disabled={generateMutation.isPending}
        >
          {generateMutation.isPending ? "Generating..." : "Generate LLM Recommendation"}
        </button>
        {generateMutation.isError ? <div className="mvp18-workspace-error">{generateMutation.error instanceof Error ? generateMutation.error.message : "Generation failed."}</div> : null}
      </div>

      <WorkspaceTable headers={["Recommendation", "Status", "Created", "Details"]}>
        {records.recommendations.map((item: WorkspaceRecommendation) => (
          <tr key={item.id}>
            <td><strong>{item.title}</strong><div className="mvp18-workspace-small">{truncate(item.recommendation_text, 220)}</div></td>
            <td>{item.status}</td>
            <td>{formatDateTime(item.created_at)}</td>
            <td>
              <details>
                <summary>View full recommendation</summary>
                <pre className="mvp18-workspace-pre">{item.ai_analysis || item.recommendation_text}</pre>
              </details>
            </td>
          </tr>
        ))}
      </WorkspaceTable>
      {records.recommendations.length === 0 ? <EmptyState label="No recommendations generated yet." /> : null}
    </div>
  );
}

type WorkspaceTabProps = {
  scopeType: WorkspaceScopeType;
  scopeId: string;
  records: WorkspaceFullRecords;
};

function WorkspaceTable({ headers, children }: { headers: string[]; children: React.ReactNode }) {
  return (
    <div className="mvp18-workspace-table-wrap">
      <table className="mvp18-workspace-table">
        <thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function RowActions({ onEdit, onDelete }: { onEdit: () => void; onDelete: () => void }) {
  return (
    <div className="mvp18-workspace-button-row compact">
      <button className="mvp18-button-secondary" onClick={onEdit}>Change</button>
      <button className="mvp18-button-danger" onClick={onDelete}>Delete</button>
    </div>
  );
}

export function Mvp18WorkspacePanel({ scopeType, scopeId }: { scopeType: WorkspaceScopeType; scopeId: string }) {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("data");
  const recordsQuery = useQuery({
    queryKey: ["mvp18-workspace-records", scopeType, scopeId],
    queryFn: () => getWorkspaceRecords(scopeType, scopeId),
    retry: 1,
  });

  const records = recordsQuery.data ?? EMPTY_RECORDS;
  const counts = useMemo(() => ({
    data: records.data_collections.length,
    questions: records.questions.length,
    findings: records.findings.length,
    analysis: records.analysis.length,
    evidence: records.evidence.length + records.files.length,
    recommendations: records.recommendations.length,
  }), [records]);

  if (recordsQuery.isLoading) return <div className="mvp18-workspace-panel">Loading workspace records...</div>;
  if (recordsQuery.isError) return <div className="mvp18-workspace-error">{recordsQuery.error instanceof Error ? recordsQuery.error.message : "Could not load workspace records."}</div>;

  return (
    <section className="mvp18-workspace-panel">
      <div className="mvp18-workspace-tabs">
        {TAB_LABELS.map((tab) => (
          <button key={tab.key} className={activeTab === tab.key ? "active" : ""} onClick={() => setActiveTab(tab.key)}>
            {tab.label} <span>{counts[tab.key] ?? 0}</span>
          </button>
        ))}
      </div>

      {activeTab === "data" ? <DataCollectionTab scopeType={scopeType} scopeId={scopeId} records={records} /> : null}
      {activeTab === "questions" ? <QuestionsTab scopeType={scopeType} scopeId={scopeId} records={records} /> : null}
      {activeTab === "findings" ? <FindingsTab scopeType={scopeType} scopeId={scopeId} records={records} /> : null}
      {activeTab === "analysis" ? <AnalysisTab scopeType={scopeType} scopeId={scopeId} records={records} /> : null}
      {activeTab === "evidence" ? <EvidenceTab scopeType={scopeType} scopeId={scopeId} records={records} /> : null}
      {activeTab === "recommendations" ? <RecommendationsTab scopeType={scopeType} scopeId={scopeId} records={records} /> : null}
    </section>
  );
}
