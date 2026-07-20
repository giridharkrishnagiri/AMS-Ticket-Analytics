from pydantic import BaseModel


class TextRefinementRequest(BaseModel):
    raw_text: str
    refinement_type: str = "finding"
    tone: str = "consulting"
    output_format: str = "structured"


class TextRefinementResponse(BaseModel):
    raw_text: str
    refined_text: str
    refinement_type: str
    tone: str
    output_format: str