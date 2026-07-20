import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { getUploadedFileDownloadUrl, uploadFile } from "./api";
import type {
  AnalysisOutput,
  DataPoint,
  EvidenceItem,
  Finding,
  StakeholderQuestion,
  Subtask,
  UploadedFile,
} from "./types";

type LinkTargetType =
  | "none"
  | "subtask"
  | "data_point"
  | "stakeholder_question"
  | "finding"
  | "analysis_output"
  | "evidence_item";

type LinkTargetOption = {
  id: string;
  label: string;
};

function formatBytes(value: number) {
  if (value < 1024) {
    return `${value} B`;
  }

  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }

  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(value: string) {
  return value.replace("T", " ").slice(0, 19);
}

function getFileLinkLabel(file: UploadedFile) {
  if (file.evidence_item_id) {
    return "Evidence Item";
  }

  if (file.analysis_output_id) {
    return "Analysis Output";
  }

  if (file.finding_id) {
    return "Finding";
  }

  if (file.stakeholder_question_id) {
    return "Stakeholder Question";
  }

  if (file.data_point_id) {
    return "Data Point";
  }

  if (file.subtask_id) {
    return "Sub-task";
  }

  return "Unlinked";
}

export function Mvp7FileUploadPanel({
  subtasks,
  dataPoints,
  stakeholderQuestions,
  findings,
  analysisOutputs,
  evidenceItems,
  uploadedFiles,
}: {
  subtasks: Subtask[];
  dataPoints: DataPoint[];
  stakeholderQuestions: StakeholderQuestion[];
  findings: Finding[];
  analysisOutputs: AnalysisOutput[];
  evidenceItems: EvidenceItem[];
  uploadedFiles: UploadedFile[];
}) {
  const queryClient = useQueryClient();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [description, setDescription] = useState("");
  const [uploadCategory, setUploadCategory] = useState("Evidence");
  const [linkTargetType, setLinkTargetType] = useState<LinkTargetType>("none");
  const [linkTargetId, setLinkTargetId] = useState("");
  const [uploadedBy, setUploadedBy] = useState("Giridhar Krishnagiri");
  const [message, setMessage] = useState("");

  const linkTargetOptions = useMemo<LinkTargetOption[]>(() => {
    if (linkTargetType === "subtask") {
      return subtasks.map((item) => ({
        id: item.id,
        label: `${item.external_id ? `${item.external_id} - ` : ""}${item.title}`,
      }));
    }

    if (linkTargetType === "data_point") {
      return dataPoints.map((item) => ({
        id: item.id,
        label: item.topic,
      }));
    }

    if (linkTargetType === "stakeholder_question") {
      return stakeholderQuestions.map((item) => ({
        id: item.id,
        label: item.question_text.length > 120 ? `${item.question_text.slice(0, 117)}...` : item.question_text,
      }));
    }

    if (linkTargetType === "finding") {
      return findings.map((item) => ({
        id: item.id,
        label: item.title,
      }));
    }

    if (linkTargetType === "analysis_output") {
      return analysisOutputs.map((item) => ({
        id: item.id,
        label: item.analysis_title,
      }));
    }

    if (linkTargetType === "evidence_item") {
      return evidenceItems.map((item) => ({
        id: item.id,
        label: item.title,
      }));
    }

    return [];
  }, [analysisOutputs, dataPoints, evidenceItems, findings, linkTargetType, stakeholderQuestions, subtasks]);

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!selectedFile) {
        throw new Error("Select a file before uploading.");
      }

      return uploadFile({
        file: selectedFile,
        description,
        upload_category: uploadCategory,
        uploaded_by: uploadedBy,
        subtask_id: linkTargetType === "subtask" ? linkTargetId : undefined,
        data_point_id: linkTargetType === "data_point" ? linkTargetId : undefined,
        stakeholder_question_id: linkTargetType === "stakeholder_question" ? linkTargetId : undefined,
        finding_id: linkTargetType === "finding" ? linkTargetId : undefined,
        analysis_output_id: linkTargetType === "analysis_output" ? linkTargetId : undefined,
        evidence_item_id: linkTargetType === "evidence_item" ? linkTargetId : undefined,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["uploaded-files"] });
      setSelectedFile(null);
      setDescription("");
      setUploadCategory("Evidence");
      setLinkTargetType("none");
      setLinkTargetId("");
      setMessage("File uploaded successfully.");
    },
    onError: (error) => {
      setMessage(error instanceof Error ? error.message : "File upload failed.");
    },
  });

  function handleUpload() {
    if (!selectedFile) {
      setMessage("Select a file before uploading.");
      return;
    }

    if (linkTargetType !== "none" && !linkTargetId) {
      setMessage("Select a record to link the uploaded file to.");
      return;
    }

    setMessage("");
    uploadMutation.mutate();
  }

  return (
    <section id="file-upload" className="content-section">
      <div className="section-header">
        <div>
          <h2>File Upload and Evidence Attachments</h2>
          <p>
            Upload supporting files and link them to sub-tasks, data points, stakeholder
            questions, findings, analysis outputs, or evidence items.
          </p>
        </div>
      </div>

      <div className="file-upload-panel">
        <div className="file-upload-grid">
          <label>
            File
            <input
              type="file"
              onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
            />
          </label>

          <label>
            Upload Category
            <select value={uploadCategory} onChange={(event) => setUploadCategory(event.target.value)}>
              <option value="Evidence">Evidence</option>
              <option value="Data Extract">Data Extract</option>
              <option value="Stakeholder Input">Stakeholder Input</option>
              <option value="Working Document">Working Document</option>
              <option value="Final Deliverable">Final Deliverable</option>
              <option value="Screenshot">Screenshot</option>
              <option value="Other">Other</option>
            </select>
          </label>

          <label>
            Link Type
            <select
              value={linkTargetType}
              onChange={(event) => {
                setLinkTargetType(event.target.value as LinkTargetType);
                setLinkTargetId("");
              }}
            >
              <option value="none">Do not link yet</option>
              <option value="subtask">Sub-task</option>
              <option value="data_point">Data Point</option>
              <option value="stakeholder_question">Stakeholder Question</option>
              <option value="finding">Finding</option>
              <option value="analysis_output">Analysis Output</option>
              <option value="evidence_item">Evidence Item</option>
            </select>
          </label>

          <label>
            Link Record
            <select
              value={linkTargetId}
              onChange={(event) => setLinkTargetId(event.target.value)}
              disabled={linkTargetType === "none"}
            >
              <option value="">
                {linkTargetType === "none" ? "No link selected" : "Select record"}
              </option>
              {linkTargetOptions.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Uploaded By
            <input
              value={uploadedBy}
              onChange={(event) => setUploadedBy(event.target.value)}
              placeholder="Uploaded by"
            />
          </label>

          <label className="file-description-field">
            Description
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Describe what this file contains and why it is useful."
            />
          </label>
        </div>

        <div className="dictation-actions">
          <button className="primary-button" onClick={handleUpload} disabled={uploadMutation.isPending}>
            {uploadMutation.isPending ? "Uploading..." : "Upload File"}
          </button>
          <button
            className="secondary-button"
            onClick={() => {
              setSelectedFile(null);
              setDescription("");
              setUploadCategory("Evidence");
              setLinkTargetType("none");
              setLinkTargetId("");
              setMessage("");
            }}
          >
            Clear
          </button>
        </div>

        {selectedFile ? (
          <div className="selected-context">
            Selected file: <strong>{selectedFile.name}</strong> ({formatBytes(selectedFile.size)})
          </div>
        ) : null}

        {message ? <div className="dictation-message">{message}</div> : null}
      </div>

      <div className="table-card wide-table uploaded-files-table">
        {uploadedFiles.length === 0 ? (
          <p className="empty-state">No uploaded files yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Category</th>
                <th>Linked To</th>
                <th>Size</th>
                <th>Uploaded By</th>
                <th>Uploaded At</th>
                <th>Download</th>
              </tr>
            </thead>
            <tbody>
              {uploadedFiles.map((item) => (
                <tr key={item.id}>
                  <td>
                    <strong>{item.original_filename}</strong>
                    {item.description ? <div className="small-note">{item.description}</div> : null}
                    {item.content_type ? <div className="small-note">{item.content_type}</div> : null}
                  </td>
                  <td>{item.upload_category ?? "-"}</td>
                  <td>{getFileLinkLabel(item)}</td>
                  <td>{formatBytes(item.file_size_bytes)}</td>
                  <td>{item.uploaded_by ?? "-"}</td>
                  <td>{formatDateTime(item.created_at)}</td>
                  <td>
                    <a
                      className="download-link"
                      href={getUploadedFileDownloadUrl(item.id)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Download
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}