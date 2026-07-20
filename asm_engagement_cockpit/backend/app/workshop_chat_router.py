from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import get_db
from app.models import Deliverable, Engagement, Subtask, Task, Workstream
from app.models.workshop_chat import (
    WorkshopChatMessage,
    WorkshopChatSession,
    WorkshopRagDocument,
    WorkshopRagLink,
)
from app.models.workshops import LlmPromptTemplate, Workshop
from app.schemas.workshop_chat import (
    WorkshopChatAskRequest,
    WorkshopChatIndexRebuildResponse,
    WorkshopChatIndexStatus,
    WorkshopChatMessageRead,
    WorkshopChatResponse,
    WorkshopChatSessionRead,
    WorkshopChatSource,
)
from app.security import require_authenticated_request

router = APIRouter(prefix="/api/ui", tags=["Workshop Chat"])

CHAT_ANSWER_PROMPT_KEY = "workshop_chat_answer"
CHAT_EXTERNAL_CONFIRMATION_PROMPT_KEY = "workshop_chat_external_confirmation"

TRANSCRIPT_CHUNK_MINUTES = 30
TRANSCRIPT_CHUNK_OVERLAP_RATIO = 1 / 6
DEFAULT_TRANSCRIPT_CHUNK_WORDS = 3500
EMBEDDING_TEXT_CHAR_LIMIT = 24000
CHAT_HISTORY_LIMIT = 8
TRANSCRIPT_SOURCE_LIMIT = 3
ENTITY_SOURCE_LIMIT = 5
LOW_CONFIDENCE_THRESHOLD = 0.23
LOCAL_EMBEDDING_MODEL = "local-hash-embedding-v1"
LOCAL_EMBEDDING_DIMENSIONS = 384

DEFAULT_CHAT_ANSWER_SYSTEM_PROMPT = (
    "You are an ASM Engagement Cockpit assistant. Answer questions using the provided "
    "workshop transcript chunks and engagement hierarchy context. Link discussion points "
    "to workstreams, deliverables, tasks, risks, dependencies, decisions, and action items "
    "when the retrieved context supports it. Do not invent internal facts. If generic "
    "knowledge is allowed, clearly label which parts are generic guidance."
)

DEFAULT_CHAT_ANSWER_USER_PROMPT = """Question:
{{question}}

Scope:
{{scope_context}}

Conversation context:
{{conversation_context}}

Retrieved internal context:
{{retrieved_context}}

Generic knowledge instruction:
{{external_knowledge_instruction}}

Answer requirements:
- Start with a direct answer.
- Use bullets or short sections when the answer has multiple points.
- Cite source labels inline, for example "(Workshop: Discovery, chunk 2)".
- When linking transcript content to workstreams, deliverables, or tasks, name both sides of the link.
- If the retrieved context is not enough, say what is missing.
- Do not expose embeddings, similarity scores, or implementation details.
"""

DEFAULT_EXTERNAL_CONFIRMATION_SYSTEM_PROMPT = (
    "Create a concise confirmation message before allowing generic model knowledge."
)

DEFAULT_EXTERNAL_CONFIRMATION_USER_PROMPT = (
    "This question appears to need generic knowledge outside the uploaded workshops and "
    "engagement data.\n\nQuestion: {{question}}\nReason: {{reason}}\n\n"
    "Ask the user whether the assistant should also use generic knowledge, and keep the "
    "message short."
)

GENERIC_KNOWLEDGE_PATTERNS = [
    r"\bbest practice\b",
    r"\bindustry\b",
    r"\bbenchmark\b",
    r"\bexplain\b",
    r"\bwhat is\b",
    r"\bhow should\b",
    r"\bhow do\b",
    r"\btemplate\b",
    r"\bexample\b",
    r"\brecommend\b",
    r"\bapproach\b",
    r"\bframework\b",
]


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def ensure_workshop_chat_prompt_templates(db: Session) -> None:
    templates = {
        CHAT_ANSWER_PROMPT_KEY: {
            "name": "Workshop Chat Answer",
            "description": (
                "Answers workshop chat questions using retrieved transcript chunks, "
                "workstreams, deliverables, and tasks."
            ),
            "system_prompt": DEFAULT_CHAT_ANSWER_SYSTEM_PROMPT,
            "user_prompt_template": DEFAULT_CHAT_ANSWER_USER_PROMPT,
        },
        CHAT_EXTERNAL_CONFIRMATION_PROMPT_KEY: {
            "name": "Workshop Chat External Knowledge Confirmation",
            "description": "Message shown before using generic knowledge outside cockpit data.",
            "system_prompt": DEFAULT_EXTERNAL_CONFIRMATION_SYSTEM_PROMPT,
            "user_prompt_template": DEFAULT_EXTERNAL_CONFIRMATION_USER_PROMPT,
        },
    }

    changed = False
    for prompt_key, data in templates.items():
        existing = db.scalar(select(LlmPromptTemplate).where(LlmPromptTemplate.prompt_key == prompt_key))
        if existing is None:
            db.add(
                LlmPromptTemplate(
                    prompt_key=prompt_key,
                    name=data["name"],
                    description=data["description"],
                    system_prompt=data["system_prompt"],
                    user_prompt_template=data["user_prompt_template"],
                    is_active=True,
                )
            )
            changed = True

    if changed:
        db.commit()


def get_chat_prompt_template(db: Session, prompt_key: str) -> LlmPromptTemplate:
    ensure_workshop_chat_prompt_templates(db)
    item = db.scalar(select(LlmPromptTemplate).where(LlmPromptTemplate.prompt_key == prompt_key))
    if item is None:
        raise HTTPException(status_code=404, detail="Chat prompt template not found")
    return item


def render_prompt(template: str, variables: dict[str, Any]) -> str:
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", normalize_text(value))
    return rendered


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, default=str)


def json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def decimal_to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def duration_minutes(workshop: Workshop) -> int | None:
    hours = decimal_to_float(workshop.duration_hours)
    if hours is None or hours <= 0:
        return None
    return max(1, int(round(hours * 60)))


def transcript_chunk_count(workshop: Workshop, words: list[str]) -> int:
    minutes = duration_minutes(workshop)
    if minutes:
        return max(1, math.ceil(minutes / TRANSCRIPT_CHUNK_MINUTES))
    return max(1, math.ceil(len(words) / DEFAULT_TRANSCRIPT_CHUNK_WORDS))


def split_transcript_into_chunks(workshop: Workshop) -> list[dict[str, Any]]:
    text = normalize_text(workshop.transcript_text)
    words = text.split()
    if not words:
        return []

    chunk_count = transcript_chunk_count(workshop, words)
    base_words = max(1, math.ceil(len(words) / chunk_count))
    overlap_words = max(50, int(base_words * TRANSCRIPT_CHUNK_OVERLAP_RATIO))
    minutes = duration_minutes(workshop)
    chunks: list[dict[str, Any]] = []

    for index in range(chunk_count):
        start_word = max(0, index * base_words - (overlap_words if index else 0))
        end_word = min(len(words), (index + 1) * base_words + (overlap_words if index < chunk_count - 1 else 0))
        chunk_text = " ".join(words[start_word:end_word]).strip()
        if not chunk_text:
            continue

        start_minute = index * TRANSCRIPT_CHUNK_MINUTES if minutes else None
        end_minute = min(minutes, (index + 1) * TRANSCRIPT_CHUNK_MINUTES) if minutes else None
        chunks.append(
            {
                "chunk_index": index + 1,
                "chunk_text": chunk_text,
                "start_minute": start_minute,
                "end_minute": end_minute,
            }
        )

    return chunks


def doc_text(title: str, fields: list[tuple[str, Any]]) -> str:
    lines = [title]
    for label, value in fields:
        normalized = normalize_text(value)
        if normalized:
            lines.append(f"{label}: {normalized}")
    return "\n".join(lines)


def source_label_for_minutes(workshop: Workshop, chunk_index: int, start_minute: int | None, end_minute: int | None) -> str:
    label = f"Workshop: {workshop.title}, chunk {chunk_index}"
    if start_minute is not None and end_minute is not None:
        label += f" ({start_minute}-{end_minute} min)"
    return label


def build_transcript_documents(db: Session) -> list[WorkshopRagDocument]:
    documents: list[WorkshopRagDocument] = []
    workshops = list(db.scalars(select(Workshop).order_by(Workshop.workshop_date.asc())).all())
    for workshop in workshops:
        for chunk in split_transcript_into_chunks(workshop):
            metadata = {
                "workshop_date": workshop.workshop_date.isoformat() if workshop.workshop_date else None,
                "functional_track": workshop.functional_track,
                "participants_text": workshop.participants_text,
                "agenda": workshop.agenda,
                "duration_hours": str(workshop.duration_hours) if workshop.duration_hours is not None else None,
            }
            title = f"{workshop.title} - chunk {chunk['chunk_index']}"
            source_label = source_label_for_minutes(
                workshop,
                chunk["chunk_index"],
                chunk["start_minute"],
                chunk["end_minute"],
            )
            content = doc_text(
                title,
                [
                    ("Workshop date", workshop.workshop_date),
                    ("Functional track", workshop.functional_track),
                    ("Participants", workshop.participants_text),
                    ("Agenda", workshop.agenda),
                    ("Transcript chunk", chunk["chunk_text"]),
                ],
            )
            documents.append(
                WorkshopRagDocument(
                    document_type="transcript_chunk",
                    source_id=workshop.id,
                    workshop_id=workshop.id,
                    title=title,
                    source_label=source_label,
                    content_text=content,
                    metadata_json=json_dumps(metadata),
                    chunk_index=chunk["chunk_index"],
                    chunk_start_minute=chunk["start_minute"],
                    chunk_end_minute=chunk["end_minute"],
                    content_hash=content_hash(content),
                )
            )
    return documents


def build_workstream_documents(db: Session) -> list[WorkshopRagDocument]:
    documents: list[WorkshopRagDocument] = []
    rows = list(db.scalars(select(Workstream).order_by(Workstream.name.asc())).all())
    for item in rows:
        engagement = db.get(Engagement, item.engagement_id)
        title = f"Workstream: {item.name}"
        content = doc_text(
            title,
            [
                ("External ID", item.external_id),
                ("Engagement", engagement.name if engagement else None),
                ("Objective", item.objective),
                ("Scope", item.scope),
                ("Status", item.status),
                ("Progress", item.progress_percent),
                ("Risks", item.risks),
                ("Dependencies", item.dependencies),
            ],
        )
        documents.append(
            WorkshopRagDocument(
                document_type="workstream",
                source_id=item.id,
                workstream_id=item.id,
                title=title,
                source_label=title,
                content_text=content,
                metadata_json=json_dumps({"engagement_id": item.engagement_id, "engagement": engagement.name if engagement else None}),
                content_hash=content_hash(content),
            )
        )
    return documents


def build_deliverable_documents(db: Session) -> list[WorkshopRagDocument]:
    documents: list[WorkshopRagDocument] = []
    rows = list(db.scalars(select(Deliverable).order_by(Deliverable.name.asc())).all())
    for item in rows:
        workstream = db.get(Workstream, item.workstream_id)
        title = f"Deliverable: {item.name}"
        content = doc_text(
            title,
            [
                ("External ID", item.external_id),
                ("Workstream", workstream.name if workstream else None),
                ("Description", item.description),
                ("Type", item.deliverable_type),
                ("Status", item.status),
                ("Review status", item.review_status),
                ("Progress", item.progress_percent),
            ],
        )
        documents.append(
            WorkshopRagDocument(
                document_type="deliverable",
                source_id=item.id,
                workstream_id=item.workstream_id,
                deliverable_id=item.id,
                title=title,
                source_label=title,
                content_text=content,
                metadata_json=json_dumps({"workstream": workstream.name if workstream else None}),
                content_hash=content_hash(content),
            )
        )
    return documents


def build_task_documents(db: Session) -> list[WorkshopRagDocument]:
    documents: list[WorkshopRagDocument] = []
    rows = list(db.scalars(select(Task).order_by(Task.title.asc())).all())
    for item in rows:
        deliverable = db.get(Deliverable, item.deliverable_id)
        workstream = db.get(Workstream, deliverable.workstream_id) if deliverable else None
        title = f"Task: {item.title}"
        content = doc_text(
            title,
            [
                ("External ID", item.external_id),
                ("Workstream", workstream.name if workstream else item.tracker_workstream_name),
                ("Deliverable", deliverable.name if deliverable else item.tracker_deliverable_name),
                ("Description", item.description),
                ("Priority", item.priority),
                ("Status", item.status),
                ("Progress", item.progress_percent),
                ("Findings", item.task_findings),
                ("Analysis", item.task_analysis),
                ("Evidence summary", item.evidence_summary),
            ],
        )
        documents.append(
            WorkshopRagDocument(
                document_type="task",
                source_id=item.id,
                workstream_id=workstream.id if workstream else None,
                deliverable_id=item.deliverable_id,
                task_id=item.id,
                title=title,
                source_label=title,
                content_text=content,
                metadata_json=json_dumps(
                    {
                        "workstream": workstream.name if workstream else item.tracker_workstream_name,
                        "deliverable": deliverable.name if deliverable else item.tracker_deliverable_name,
                    }
                ),
                content_hash=content_hash(content),
            )
        )
    return documents


def build_subtask_documents(db: Session) -> list[WorkshopRagDocument]:
    documents: list[WorkshopRagDocument] = []
    rows = list(db.scalars(select(Subtask).order_by(Subtask.title.asc())).all())
    for item in rows:
        task = db.get(Task, item.task_id)
        deliverable = db.get(Deliverable, task.deliverable_id) if task else None
        workstream = db.get(Workstream, deliverable.workstream_id) if deliverable else None
        title = f"Sub-task: {item.title}"
        content = doc_text(
            title,
            [
                ("External ID", item.external_id),
                ("Workstream", workstream.name if workstream else None),
                ("Deliverable", deliverable.name if deliverable else None),
                ("Task", task.title if task else None),
                ("Description", item.description),
                ("Completion criteria", item.completion_criteria),
                ("Priority", item.priority),
                ("Status", item.status),
                ("Findings", item.findings),
                ("Analysis", item.analysis),
            ],
        )
        documents.append(
            WorkshopRagDocument(
                document_type="subtask",
                source_id=item.id,
                workstream_id=workstream.id if workstream else None,
                deliverable_id=deliverable.id if deliverable else None,
                task_id=item.task_id,
                subtask_id=item.id,
                title=title,
                source_label=title,
                content_text=content,
                metadata_json=json_dumps(
                    {
                        "workstream": workstream.name if workstream else None,
                        "deliverable": deliverable.name if deliverable else None,
                        "task": task.title if task else None,
                    }
                ),
                content_hash=content_hash(content),
            )
        )
    return documents


def build_index_documents(db: Session) -> list[WorkshopRagDocument]:
    documents = build_transcript_documents(db)
    documents.extend(build_workstream_documents(db))
    documents.extend(build_deliverable_documents(db))
    documents.extend(build_task_documents(db))
    documents.extend(build_subtask_documents(db))
    return documents


def get_openai_client() -> Any:
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=400,
            detail="OPENAI_API_KEY is not configured. Add it to backend/.env and restart the backend.",
        )

    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key)


def embedding_input(document: WorkshopRagDocument) -> str:
    return document.content_text[:EMBEDDING_TEXT_CHAR_LIMIT]


def local_hash_embedding(text: str) -> list[float]:
    vector = [0.0] * LOCAL_EMBEDDING_DIMENSIONS
    tokens = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,}", text.lower())
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % LOCAL_EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def local_hash_embeddings(texts: list[str]) -> list[list[float]]:
    return [local_hash_embedding(text) for text in texts]


def embed_texts(texts: list[str]) -> list[list[float]]:
    embeddings, _ = embed_texts_for_model(texts, get_settings().openai_embedding_model, allow_fallback=True)
    return embeddings


def embed_texts_for_model(
    texts: list[str],
    model: str,
    allow_fallback: bool,
) -> tuple[list[list[float]], str]:
    if not texts:
        return [], model

    if model == LOCAL_EMBEDDING_MODEL:
        return local_hash_embeddings(texts), LOCAL_EMBEDDING_MODEL

    if allow_fallback and not get_settings().openai_api_key:
        return local_hash_embeddings(texts), LOCAL_EMBEDDING_MODEL

    client = get_openai_client()
    embeddings: list[list[float]] = []
    batch_size = 32
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        try:
            response = client.embeddings.create(model=model, input=batch)
        except Exception as exc:
            if allow_fallback:
                return local_hash_embeddings(texts), LOCAL_EMBEDDING_MODEL
            raise HTTPException(status_code=502, detail=f"Embedding generation failed: {type(exc).__name__}: {exc}") from exc
        embeddings.extend([list(item.embedding) for item in response.data])
    return embeddings, model


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def document_embedding(document: WorkshopRagDocument) -> list[float]:
    return json_loads(document.embedding_json, [])


def rebuild_workshop_chat_index(db: Session) -> WorkshopChatIndexRebuildResponse:
    settings = get_settings()
    documents = build_index_documents(db)
    embeddings, embedding_model = embed_texts_for_model(
        [embedding_input(document) for document in documents],
        settings.openai_embedding_model,
        allow_fallback=True,
    )

    db.execute(delete(WorkshopRagLink))
    db.execute(delete(WorkshopRagDocument))

    indexed_at = datetime.utcnow()
    for document, embedding in zip(documents, embeddings):
        document.embedding_model = embedding_model
        document.embedding_json = json_dumps(embedding)
        document.indexed_at = indexed_at
        db.add(document)

    db.flush()
    build_transcript_entity_links(db, documents)
    db.commit()
    return index_status(db, rebuilt=True, message=f"Indexed {len(documents)} search documents.")


def build_transcript_entity_links(db: Session, documents: list[WorkshopRagDocument]) -> None:
    transcript_docs = [item for item in documents if item.document_type == "transcript_chunk"]
    entity_docs = [item for item in documents if item.document_type != "transcript_chunk"]

    entity_embeddings = [(item, document_embedding(item)) for item in entity_docs]
    for transcript_doc in transcript_docs:
        transcript_embedding = document_embedding(transcript_doc)
        scored: list[tuple[float, WorkshopRagDocument]] = []
        for entity_doc, entity_embedding in entity_embeddings:
            score = cosine_similarity(transcript_embedding, entity_embedding)
            if score > 0.01:
                scored.append((score, entity_doc))

        for score, entity_doc in sorted(scored, key=lambda row: row[0], reverse=True)[:5]:
            db.add(
                WorkshopRagLink(
                    transcript_document_id=transcript_doc.id,
                    entity_document_id=entity_doc.id,
                    score=score,
                    reason="Semantic similarity between transcript chunk and engagement entity.",
                )
            )


def indexed_embedding_model(db: Session) -> str | None:
    row = db.execute(
        select(WorkshopRagDocument.embedding_model, func.count().label("count"))
        .where(WorkshopRagDocument.embedding_model.is_not(None))
        .group_by(WorkshopRagDocument.embedding_model)
        .order_by(func.count().desc())
    ).first()
    return row[0] if row else None


def index_status(db: Session, rebuilt: bool | None = None, message: str | None = None) -> Any:
    settings = get_settings()
    document_count = db.scalar(select(func.count()).select_from(WorkshopRagDocument)) or 0
    transcript_count = (
        db.scalar(
            select(func.count()).select_from(WorkshopRagDocument).where(WorkshopRagDocument.document_type == "transcript_chunk")
        )
        or 0
    )
    link_count = db.scalar(select(func.count()).select_from(WorkshopRagLink)) or 0
    last_indexed_at = db.scalar(select(func.max(WorkshopRagDocument.indexed_at)))
    active_embedding_model = indexed_embedding_model(db) or settings.openai_embedding_model
    payload = {
        "document_count": document_count,
        "transcript_chunk_count": transcript_count,
        "entity_document_count": max(0, document_count - transcript_count),
        "link_count": link_count,
        "last_indexed_at": last_indexed_at,
        "embedding_model": active_embedding_model,
    }
    if rebuilt is None:
        return WorkshopChatIndexStatus(**payload)
    return WorkshopChatIndexRebuildResponse(rebuilt=rebuilt, message=message or "", **payload)


def scope_label(db: Session, scope_type: str, scope_id: uuid.UUID | None) -> str:
    if scope_type == "all" or scope_id is None:
        return "All workshops and engagement records"
    model_map: dict[str, Any] = {
        "workshop": Workshop,
        "workstream": Workstream,
        "deliverable": Deliverable,
        "task": Task,
        "subtask": Subtask,
    }
    model = model_map.get(scope_type)
    item = db.get(model, scope_id) if model is not None else None
    if item is None:
        return f"{scope_type}: {scope_id}"
    label = getattr(item, "title", None) or getattr(item, "name", None) or str(scope_id)
    return f"{scope_type}: {label}"


def scope_match(document: WorkshopRagDocument, scope_type: str, scope_id: uuid.UUID | None) -> bool:
    if scope_type == "all" or scope_id is None:
        return True
    field_map = {
        "workshop": document.workshop_id,
        "workstream": document.workstream_id,
        "deliverable": document.deliverable_id,
        "task": document.task_id,
        "subtask": document.subtask_id,
    }
    return field_map.get(scope_type) == scope_id


def scope_boost(document: WorkshopRagDocument, scope_type: str, scope_id: uuid.UUID | None) -> float:
    if scope_type == "all" or scope_id is None:
        return 0.0
    if scope_match(document, scope_type, scope_id):
        return 0.08
    if document.document_type == "transcript_chunk":
        return 0.0
    return -0.03


def retrieve_documents(db: Session, question: str, request: WorkshopChatAskRequest) -> tuple[list[WorkshopRagDocument], list[WorkshopRagDocument], dict[uuid.UUID, float]]:
    settings = get_settings()
    active_embedding_model = indexed_embedding_model(db) or settings.openai_embedding_model
    docs = list(
        db.scalars(
            select(WorkshopRagDocument).where(
                WorkshopRagDocument.embedding_model == active_embedding_model,
                WorkshopRagDocument.embedding_json.is_not(None),
            )
        ).all()
    )
    if not docs:
        rebuild_workshop_chat_index(db)
        active_embedding_model = indexed_embedding_model(db) or settings.openai_embedding_model
        docs = list(
            db.scalars(
                select(WorkshopRagDocument).where(
                    WorkshopRagDocument.embedding_model == active_embedding_model,
                    WorkshopRagDocument.embedding_json.is_not(None),
                )
            ).all()
        )

    query_embeddings, used_model = embed_texts_for_model([question], active_embedding_model, allow_fallback=True)
    if used_model != active_embedding_model:
        rebuild_workshop_chat_index(db)
        active_embedding_model = used_model
        docs = list(
            db.scalars(
                select(WorkshopRagDocument).where(
                    WorkshopRagDocument.embedding_model == active_embedding_model,
                    WorkshopRagDocument.embedding_json.is_not(None),
                )
            ).all()
        )
        query_embeddings, _ = embed_texts_for_model([question], active_embedding_model, allow_fallback=False)
    query_embedding = query_embeddings[0]
    scores: dict[uuid.UUID, float] = {}
    scored_docs: list[tuple[float, WorkshopRagDocument]] = []
    for document in docs:
        score = cosine_similarity(query_embedding, document_embedding(document))
        score += scope_boost(document, request.scope_type, request.scope_id)
        scores[document.id] = score
        scored_docs.append((score, document))

    transcripts = [
        document
        for score, document in sorted(scored_docs, key=lambda row: row[0], reverse=True)
        if document.document_type == "transcript_chunk"
    ][:TRANSCRIPT_SOURCE_LIMIT]

    entities = [
        document
        for score, document in sorted(scored_docs, key=lambda row: row[0], reverse=True)
        if document.document_type != "transcript_chunk"
    ][:ENTITY_SOURCE_LIMIT]

    linked_entities = linked_entities_for_transcripts(db, transcripts, scores)
    entity_by_id = {item.id: item for item in entities}
    for item in linked_entities:
        entity_by_id[item.id] = item

    return transcripts, list(entity_by_id.values())[:ENTITY_SOURCE_LIMIT], scores


def linked_entities_for_transcripts(
    db: Session,
    transcripts: list[WorkshopRagDocument],
    scores: dict[uuid.UUID, float],
) -> list[WorkshopRagDocument]:
    if not transcripts:
        return []
    transcript_ids = [item.id for item in transcripts]
    rows = list(
        db.scalars(
            select(WorkshopRagLink)
            .where(WorkshopRagLink.transcript_document_id.in_(transcript_ids))
            .order_by(WorkshopRagLink.score.desc())
            .limit(ENTITY_SOURCE_LIMIT)
        ).all()
    )
    linked: list[WorkshopRagDocument] = []
    for row in rows:
        document = db.get(WorkshopRagDocument, row.entity_document_id)
        if document is not None:
            scores[document.id] = max(scores.get(document.id, 0.0), float(row.score))
            linked.append(document)
    return linked


def source_snippet(text: str, limit: int = 420) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."


def to_source(document: WorkshopRagDocument, score: float) -> WorkshopChatSource:
    return WorkshopChatSource(
        id=document.id,
        document_type=document.document_type,
        title=document.title,
        source_label=document.source_label,
        score=round(score, 4),
        snippet=source_snippet(document.content_text),
        workshop_id=document.workshop_id,
        workstream_id=document.workstream_id,
        deliverable_id=document.deliverable_id,
        task_id=document.task_id,
        subtask_id=document.subtask_id,
        chunk_index=document.chunk_index,
        chunk_start_minute=document.chunk_start_minute,
        chunk_end_minute=document.chunk_end_minute,
    )


def retrieved_context(sources: list[WorkshopChatSource]) -> str:
    if not sources:
        return "No relevant internal context was retrieved."
    blocks = []
    for source in sources:
        blocks.append(
            "\n".join(
                [
                    f"Source: {source.source_label}",
                    f"Type: {source.document_type}",
                    f"Relevance score: {source.score}",
                    f"Content: {source.snippet}",
                ]
            )
        )
    return "\n\n".join(blocks)


def conversation_context(messages: list[WorkshopChatMessage]) -> str:
    if not messages:
        return "No prior chat context."
    recent = messages[-CHAT_HISTORY_LIMIT:]
    return "\n".join(f"{message.role}: {message.content}" for message in recent)


def needs_generic_knowledge(question: str, sources: list[WorkshopChatSource]) -> tuple[bool, str | None]:
    normalized = question.lower()
    best_score = max([source.score for source in sources], default=0.0)
    has_internal_context = bool(sources)
    pattern_match = any(re.search(pattern, normalized) for pattern in GENERIC_KNOWLEDGE_PATTERNS)
    if pattern_match and best_score < 0.35:
        return True, "The question asks for general guidance and the internal context match is limited."
    if not has_internal_context and best_score < LOW_CONFIDENCE_THRESHOLD:
        return True, "The available workshop and engagement index has low confidence for this question."
    return False, None


def external_confirmation_message(db: Session, question: str, reason: str) -> str:
    template = get_chat_prompt_template(db, CHAT_EXTERNAL_CONFIRMATION_PROMPT_KEY)
    return render_prompt(template.user_prompt_template, {"question": question, "reason": reason})


def select_chat_model(request: WorkshopChatAskRequest, sources: list[WorkshopChatSource]) -> str:
    settings = get_settings()
    has_transcript = any(source.document_type == "transcript_chunk" for source in sources)
    has_entity = any(source.document_type != "transcript_chunk" for source in sources)
    scoped_entity = request.scope_type in {"workstream", "deliverable", "task", "subtask"}
    if request.force_deep_context or (has_transcript and has_entity and scoped_entity):
        return settings.openai_deep_chat_model
    return settings.openai_chat_model


def quota_or_availability_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        marker in text
        for marker in [
            "insufficient_quota",
            "current quota",
            "model_not_found",
            "does not exist",
            "not have access",
        ]
    )


def extractive_fallback_answer(question: str, sources: list[WorkshopChatSource]) -> str:
    if not sources:
        return (
            "I could not generate a model-based response, and no relevant indexed workshop "
            "or work-item context was retrieved for this question."
        )

    transcript_sources = [source for source in sources if source.document_type == "transcript_chunk"]
    entity_sources = [source for source in sources if source.document_type != "transcript_chunk"]
    lines = [
        "I could not generate a model-based response because the configured OpenAI model is not currently available. "
        "Here are the most relevant indexed internal references for your question.",
        "",
        f"Question: {question}",
    ]

    if transcript_sources:
        lines.append("")
        lines.append("Transcript references:")
        for source in transcript_sources[:TRANSCRIPT_SOURCE_LIMIT]:
            lines.append(f"- {source.source_label}: {source.snippet}")

    if entity_sources:
        lines.append("")
        lines.append("Linked work items:")
        for source in entity_sources[:ENTITY_SOURCE_LIMIT]:
            lines.append(f"- {source.source_label}: {source.snippet}")

    return "\n".join(lines)


def run_chat_llm(
    db: Session,
    question: str,
    request: WorkshopChatAskRequest,
    messages: list[WorkshopChatMessage],
    sources: list[WorkshopChatSource],
) -> tuple[str, str]:
    template = get_chat_prompt_template(db, CHAT_ANSWER_PROMPT_KEY)
    model = select_chat_model(request, sources)
    external_instruction = (
        "Generic model knowledge is allowed. Clearly label any generic guidance and separate it from internal cockpit facts."
        if request.allow_external_knowledge
        else "Generic model knowledge is not allowed. Answer only from retrieved internal context."
    )
    user_prompt = render_prompt(
        template.user_prompt_template,
        {
            "question": question,
            "scope_context": scope_label(db, request.scope_type, request.scope_id),
            "conversation_context": conversation_context(messages),
            "retrieved_context": retrieved_context(sources),
            "external_knowledge_instruction": external_instruction,
        },
    )

    client = get_openai_client()
    settings = get_settings()
    fallback_model = settings.openai_model
    last_error: Exception | None = None
    response = None
    model_used = model
    for candidate_model in [model, fallback_model]:
        if candidate_model == model_used and last_error is not None:
            continue
        try:
            response = client.responses.create(
                model=candidate_model,
                input=[
                    {"role": "system", "content": template.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            model_used = candidate_model
            break
        except Exception as exc:
            last_error = exc

    if response is None:
        error = last_error or RuntimeError("No response returned.")
        if quota_or_availability_error(error):
            return extractive_fallback_answer(question, sources), "extractive-fallback"
        raise HTTPException(status_code=502, detail=f"Workshop chat LLM failed: {type(error).__name__}: {error}") from error

    answer = normalize_text(getattr(response, "output_text", ""))
    if not answer:
        answer = str(response)
    return answer, model_used


def get_or_create_session(
    db: Session,
    request: WorkshopChatAskRequest,
    user: dict[str, Any],
) -> WorkshopChatSession:
    if request.session_id:
        existing = db.scalar(
            select(WorkshopChatSession)
            .options(selectinload(WorkshopChatSession.messages))
            .where(WorkshopChatSession.id == request.session_id)
        )
        if existing is not None:
            return existing

    session = WorkshopChatSession(
        title=normalize_text(request.question)[:120],
        scope_type=request.scope_type,
        scope_id=request.scope_id,
        created_by=user.get("display_name") or user.get("username"),
    )
    db.add(session)
    db.flush()
    return session


def add_chat_message(
    db: Session,
    session: WorkshopChatSession,
    role: str,
    content: str,
    model_used: str | None = None,
    sources: list[WorkshopChatSource] | None = None,
) -> WorkshopChatMessage:
    message = WorkshopChatMessage(
        session_id=session.id,
        role=role,
        content=content,
        model_used=model_used,
        source_context_json=json_dumps([source.model_dump(mode="json") for source in sources or []]),
    )
    db.add(message)
    session.updated_at = datetime.utcnow()
    db.flush()
    return message


def message_reads(session: WorkshopChatSession) -> list[WorkshopChatMessageRead]:
    return [WorkshopChatMessageRead.model_validate(message) for message in session.messages]


@router.get("/workshop-chat/index-status", response_model=WorkshopChatIndexStatus)
def get_workshop_chat_index_status(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> WorkshopChatIndexStatus:
    ensure_workshop_chat_prompt_templates(db)
    return index_status(db)


@router.post("/workshop-chat/rebuild-index", response_model=WorkshopChatIndexRebuildResponse)
def rebuild_workshop_chat_index_endpoint(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> WorkshopChatIndexRebuildResponse:
    ensure_workshop_chat_prompt_templates(db)
    return rebuild_workshop_chat_index(db)


@router.get("/workshop-chat/sessions/{session_id}", response_model=WorkshopChatSessionRead)
def get_workshop_chat_session(
    session_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> WorkshopChatSession:
    session = db.scalar(
        select(WorkshopChatSession)
        .options(selectinload(WorkshopChatSession.messages))
        .where(WorkshopChatSession.id == session_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Workshop chat session not found")
    return session


@router.post("/workshop-chat/ask", response_model=WorkshopChatResponse)
def ask_workshop_chat(
    request: WorkshopChatAskRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(require_authenticated_request)],
) -> WorkshopChatResponse:
    ensure_workshop_chat_prompt_templates(db)
    question = normalize_text(request.question)
    if not question:
        raise HTTPException(status_code=422, detail="Question is required.")

    session = get_or_create_session(db, request, user)
    prior_messages = list(session.messages)
    add_chat_message(db, session, "user", question)

    transcript_docs, entity_docs, scores = retrieve_documents(db, question, request)
    source_docs = transcript_docs + entity_docs
    sources = [to_source(document, scores.get(document.id, 0.0)) for document in source_docs]
    linked_entities = [
        source
        for source in sources
        if source.document_type != "transcript_chunk"
    ]
    requires_external, external_reason = needs_generic_knowledge(question, sources)

    if requires_external and not request.allow_external_knowledge:
        answer = external_confirmation_message(db, question, external_reason or "Generic knowledge may improve the answer.")
        add_chat_message(db, session, "assistant", answer, sources=sources)
        db.commit()
        db.refresh(session)
        return WorkshopChatResponse(
            session_id=session.id,
            answer=answer,
            requires_external_knowledge=True,
            external_knowledge_reason=external_reason,
            model_used=None,
            search_order=[
                "Detected low-confidence or generic-knowledge question",
                "Retrieved internal transcript/entity context",
                "Requested user confirmation before using generic knowledge",
            ],
            sources=sources,
            linked_entities=linked_entities,
            messages=message_reads(session),
        )

    answer, model_used = run_chat_llm(db, question, request, prior_messages, sources)
    add_chat_message(db, session, "assistant", answer, model_used=model_used, sources=sources)
    db.commit()
    db.refresh(session)
    return WorkshopChatResponse(
        session_id=session.id,
        answer=answer,
        requires_external_knowledge=False,
        external_knowledge_reason=None,
        model_used=model_used,
        search_order=[
            "Resolved workstream/deliverable/task scope",
            "Retrieved top transcript chunks",
            "Retrieved and linked engagement entities",
            "Generated response with Luna or Terra based on context depth",
        ],
        sources=sources,
        linked_entities=linked_entities,
        messages=message_reads(session),
    )
