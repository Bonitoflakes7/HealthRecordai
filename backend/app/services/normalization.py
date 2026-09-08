import re
from datetime import date, datetime

from backend.app.models.clinical import DocumentSection, DocumentType, NormalizedDocument, Observation


class DocumentNormalizer:
    """Create conservative structure from extracted text without clinical inference."""

    _date_pattern = re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b")
    _written_date_pattern = re.compile(r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b", re.I)
    _observation_patterns = (
        ("blood_pressure", re.compile(r"\b(?:blood pressure|bp)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})\s*(mmhg)?\b", re.I), None),
        ("heart_rate", re.compile(r"\b(?:heart rate|pulse(?: rate)?)\s*[:=]?\s*(\d{2,3})\s*(bpm)?\b", re.I), "bpm"),
        ("temperature", re.compile(r"\btemperature\s*[:=]?\s*(\d{2,3}(?:\.\d+)?)\s*(°?c|°?f)?\b", re.I), None),
        ("glucose", re.compile(r"\b(?:blood )?glucose\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(mg/dl|mmol/l)?\b", re.I), None),
        ("hba1c", re.compile(r"\bhba1c\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%?\b", re.I), "%"),
    )

    def normalize(self, record_id: str, text: str) -> NormalizedDocument:
        cleaned = text.strip()
        return NormalizedDocument(
            record_id=record_id,
            document_type=self._classify(cleaned),
            title=self._title(cleaned),
            document_date=self._first_date(cleaned),
            sections=self._sections(cleaned),
            observations=self._observations(cleaned),
        )

    @staticmethod
    def _classify(text: str) -> DocumentType:
        lowered = re.split(r"\bDISCLAIMER\b", text, maxsplit=1, flags=re.I)[0].lower()
        lowered = re.sub(r"[*_`]", "", lowered)
        scores: dict[DocumentType, int] = {
            "lab_report": sum(word in lowered for word in ("laboratory", "lab result", "reference range", "specimen")),
            "prescription": sum(word in lowered for word in ("prescription", "dosage", "refill", "sig:")),
            "discharge_summary": sum(word in lowered for word in ("discharge summary", "discharged", "hospital course")),
            "imaging_report": sum(word in lowered for word in ("impression:", "radiology", "findings:", "imaging")),
            "clinical_note": sum(word in lowered for word in ("assessment", "plan", "chief complaint", "clinical note", "vital signs", "clinical examination")),
        }
        document_type, score = max(scores.items(), key=lambda item: item[1])
        return document_type if score else "unknown"

    @staticmethod
    def _title(text: str) -> str | None:
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        return re.sub(r"[*_`]", "", first_line).strip()[:160] or None

    @classmethod
    def _first_date(cls, text: str) -> date | None:
        match = cls._date_pattern.search(text)
        if match:
            try:
                return date(*(int(part) for part in match.groups()))
            except ValueError:
                return None
        written = cls._written_date_pattern.search(text)
        if written:
            try:
                return datetime.strptime(written.group(0), "%d %B %Y").date()
            except ValueError:
                return None
        return None

    @staticmethod
    def _sections(text: str) -> list[DocumentSection]:
        sections: list[DocumentSection] = []
        heading: str | None = None
        body: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            clean_line = re.sub(r"[*_`]", "", line).strip()
            is_markdown_heading = line.startswith("**") and line.endswith("**")
            is_heading = bool(clean_line) and (is_markdown_heading or clean_line.endswith(":") or (clean_line.isupper() and len(clean_line) <= 80))
            if is_heading:
                if heading and "\n".join(body).strip():
                    sections.append(DocumentSection(heading=heading.rstrip(": "), text="\n".join(body).strip()))
                heading = clean_line
                body = []
            elif line:
                body.append(line)
        if heading and "\n".join(body).strip():
            sections.append(DocumentSection(heading=heading.rstrip(": "), text="\n".join(body).strip()))
        if not sections and text.strip():
            sections.append(DocumentSection(heading="Document", text=text.strip()))
        return sections

    @classmethod
    def _observations(cls, text: str) -> list[Observation]:
        observed_on = cls._first_date(text)
        observations: list[Observation] = []
        for name, pattern, default_unit in cls._observation_patterns:
            match = pattern.search(text)
            if not match:
                continue
            value = match.group(1)
            if name == "blood_pressure":
                value = f"{match.group(1)}/{match.group(2)}"
            if default_unit:
                unit = default_unit
            elif name == "blood_pressure":
                unit = "mmHg" if len(match.groups()) > 2 and match.group(3) else None
            else:
                unit = next((group for group in match.groups()[1:] if group), None)
            observations.append(
                Observation(name=name, value=value, unit=unit, observed_on=observed_on, source_text=match.group(0))
            )
        return observations
