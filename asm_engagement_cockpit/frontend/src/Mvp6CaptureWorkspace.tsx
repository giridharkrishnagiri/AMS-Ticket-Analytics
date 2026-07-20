import { useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createAnalysisOutput, createFinding, refineText } from "./api";
import type { Subtask } from "./types";

type SpeechRecognitionType = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onend: (() => void) | null;
};

type SpeechRecognitionEventLike = {
  results: {
    length: number;
    [index: number]: {
      isFinal: boolean;
      [index: number]: {
        transcript: string;
      };
    };
  };
};

type WindowWithSpeechRecognition = Window & {
  SpeechRecognition?: new () => SpeechRecognitionType;
  webkitSpeechRecognition?: new () => SpeechRecognitionType;
};

function getSpeechRecognitionConstructor() {
  const typedWindow = window as WindowWithSpeechRecognition;
  return typedWindow.SpeechRecognition ?? typedWindow.webkitSpeechRecognition;
}

function extractTitle(text: string, fallback: string) {
  const firstMeaningfulLine = text
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line && !line.endsWith(":"));

  if (!firstMeaningfulLine) {
    return fallback;
  }

  return firstMeaningfulLine.length > 120
    ? `${firstMeaningfulLine.slice(0, 117)}...`
    : firstMeaningfulLine;
}

function appendText(current: string, incoming: string) {
  if (!current.trim()) {
    return incoming.trim();
  }

  return `${current.trim()}\n${incoming.trim()}`;
}

export function Mvp6CaptureWorkspace({ subtasks }: { subtasks: Subtask[] }) {
  const queryClient = useQueryClient();

  const [selectedSubtaskId, setSelectedSubtaskId] = useState("");
  const [captureMode, setCaptureMode] = useState<"finding" | "analysis">("finding");
  const [rawText, setRawText] = useState("");
  const [refinedText, setRefinedText] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [dictationMessage, setDictationMessage] = useState("");

  const recognitionRef = useRef<SpeechRecognitionType | null>(null);

  const selectedSubtask = useMemo(
    () => subtasks.find((item) => item.id === selectedSubtaskId) ?? null,
    [selectedSubtaskId, subtasks],
  );

  const refineMutation = useMutation({
    mutationFn: () =>
      refineText({
        raw_text: rawText,
        refinement_type: captureMode,
        tone: "consulting",
        output_format: "structured",
      }),
    onSuccess: (response) => {
      setRefinedText(response.refined_text);
    },
  });

  const saveFindingMutation = useMutation({
    mutationFn: () =>
      createFinding({
        subtask_id: selectedSubtaskId,
        title: extractTitle(refinedText || rawText, "Dictated finding"),
        finding_type: "Dictated Finding",
        severity: "Medium",
        finding_text: refinedText || rawText,
        status: "Draft",
        confidence_level: "Medium",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["findings"] });
      setDictationMessage("Finding saved successfully.");
    },
  });

  const saveAnalysisMutation = useMutation({
    mutationFn: () =>
      createAnalysisOutput({
        subtask_id: selectedSubtaskId,
        analysis_title: extractTitle(refinedText || rawText, "Dictated analysis"),
        analysis_type: "Dictated Analysis",
        analysis_text: refinedText || rawText,
        status: "Draft",
        confidence_level: "Medium",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analysis-outputs"] });
      setDictationMessage("Analysis output saved successfully.");
    },
  });

  function startDictation() {
    const SpeechRecognitionConstructor = getSpeechRecognitionConstructor();

    if (!SpeechRecognitionConstructor) {
      setDictationMessage("Speech recognition is not available in this browser. Use Chrome or Edge, or type into the text box.");
      return;
    }

    const recognition = new SpeechRecognitionConstructor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (event) => {
      let finalTranscript = "";
      let interimTranscript = "";

      for (let index = 0; index < event.results.length; index += 1) {
        const result = event.results[index];
        const transcript = result[0]?.transcript ?? "";

        if (result.isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      if (finalTranscript.trim()) {
        setRawText((current) => appendText(current, finalTranscript));
      }

      if (interimTranscript.trim()) {
        setDictationMessage(`Listening: ${interimTranscript.trim()}`);
      }
    };

    recognition.onerror = () => {
      setIsListening(false);
      setDictationMessage("Dictation stopped because the browser reported a speech recognition error.");
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
    setDictationMessage("Listening. Speak clearly into your microphone.");
  }

  function stopDictation() {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setIsListening(false);
    setDictationMessage("Dictation stopped.");
  }

  function replaceRawWithRefined() {
    setRawText(refinedText);
  }

  function appendRefinedToRaw() {
    setRawText((current) => appendText(current, refinedText));
  }

  function clearWorkspace() {
    setRawText("");
    setRefinedText("");
    setDictationMessage("");
  }

  function saveOutput() {
    if (!selectedSubtaskId) {
      setDictationMessage("Select a sub-task before saving.");
      return;
    }

    if (!(refinedText || rawText).trim()) {
      setDictationMessage("Enter or dictate text before saving.");
      return;
    }

    if (captureMode === "finding") {
      saveFindingMutation.mutate();
      return;
    }

    saveAnalysisMutation.mutate();
  }

  const isSaving = saveFindingMutation.isPending || saveAnalysisMutation.isPending;

  return (
    <section id="dictation-refinement" className="content-section">
      <div className="section-header">
        <div>
          <h2>Dictation and Refinement Workspace</h2>
          <p>
            Dictate or type rough consulting notes, refine them, edit the refined output,
            then save as a new finding or analysis output.
          </p>
        </div>
      </div>

      <div className="capture-workspace">
        <div className="capture-controls">
          <label>
            Capture Type
            <select value={captureMode} onChange={(event) => setCaptureMode(event.target.value as "finding" | "analysis")}>
              <option value="finding">Finding</option>
              <option value="analysis">Analysis Output</option>
            </select>
          </label>

          <label>
            Link to Sub-task
            <select value={selectedSubtaskId} onChange={(event) => setSelectedSubtaskId(event.target.value)}>
              <option value="">Select a sub-task</option>
              {subtasks.map((item) => (
                <option key={item.id} value={item.id}>
                  {(item.external_id ? `${item.external_id} - ` : "") + item.title}
                </option>
              ))}
            </select>
          </label>
        </div>

        {selectedSubtask ? (
          <div className="selected-context">
            Selected context: <strong>{selectedSubtask.external_id ? `${selectedSubtask.external_id} - ` : ""}{selectedSubtask.title}</strong>
          </div>
        ) : (
          <div className="selected-context warning-context">
            Select a sub-task before saving the refined output.
          </div>
        )}

        <div className="dictation-actions">
          <button className="secondary-button" onClick={startDictation} disabled={isListening}>
            Start Dictation
          </button>
          <button className="secondary-button" onClick={stopDictation} disabled={!isListening}>
            Stop Dictation
          </button>
          <button className="primary-button" onClick={() => refineMutation.mutate()} disabled={!rawText.trim() || refineMutation.isPending}>
            {refineMutation.isPending ? "Refining..." : "Refine Text"}
          </button>
          <button className="secondary-button" onClick={clearWorkspace}>
            Clear
          </button>
        </div>

        {dictationMessage ? <div className="dictation-message">{dictationMessage}</div> : null}

        <div className="capture-grid">
          <label className="text-area-label">
            Raw dictated / typed text
            <textarea
              value={rawText}
              onChange={(event) => setRawText(event.target.value)}
              placeholder="Dictate or type rough notes here..."
            />
          </label>

          <label className="text-area-label">
            Editable refined output
            <textarea
              value={refinedText}
              onChange={(event) => setRefinedText(event.target.value)}
              placeholder="Refined output appears here. You can edit it before saving."
            />
          </label>
        </div>

        <div className="dictation-actions">
          <button className="secondary-button" onClick={replaceRawWithRefined} disabled={!refinedText.trim()}>
            Replace Raw with Refined
          </button>
          <button className="secondary-button" onClick={appendRefinedToRaw} disabled={!refinedText.trim()}>
            Append Refined to Raw
          </button>
          <button className="primary-button" onClick={saveOutput} disabled={isSaving || !selectedSubtaskId || !(rawText.trim() || refinedText.trim())}>
            {isSaving ? "Saving..." : captureMode === "finding" ? "Save as Finding" : "Save as Analysis Output"}
          </button>
        </div>
      </div>
    </section>
  );
}