from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from backend.app.models.retrieval import SearchResponse
from backend.app.models.qa import AskRequest, AskResponse
from backend.app.models.timeline import TimelineResponse
from backend.app.models.analytics import AnalyticsResponse
from backend.app.models.literature import LiteratureAskRequest, LiteratureAskResponse, LiteratureSearchResponse
from backend.app.services.pubmed import LiteratureUnavailable
from backend.app.services.safety import SafetyChecker
from backend.app.models.schemas import HealthResponse, RecordDetail, RecordListResponse
from backend.app.services.records import RecordStore
from backend.app.models.auth import AuditResponse, Token, User, UserRegistration
from backend.app.services.security import create_access_token, decode_access_token


router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def get_store(request: Request) -> RecordStore:
    return request.app.state.record_store


def current_user(request: Request, token: str | None = Depends(oauth2_scheme)) -> User:
    if not request.app.state.settings.auth_enabled:
        return User(id="dev-user", username="development")
    if not token:
        raise HTTPException(status_code=401, detail="authentication required", headers={"WWW-Authenticate": "Bearer"})
    user_id = decode_access_token(token)
    user = request.app.state.auth_store.get(user_id) if user_id else None
    if user is None or user.disabled:
        raise HTTPException(status_code=401, detail="invalid authentication credentials", headers={"WWW-Authenticate": "Bearer"})
    return user


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(status="ok", app=settings.app_name, env=settings.app_env, phase="phase-11-security")


@router.post("/api/v1/auth/register", response_model=User, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegistration, request: Request) -> User:
    try:
        user = request.app.state.auth_store.create_user(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    request.app.state.audit_store.record(user.id, "auth.register", "user", user.id)
    return user


@router.post("/api/v1/auth/token", response_model=Token)
def token(request: Request, form: OAuth2PasswordRequestForm = Depends()) -> Token:
    user = request.app.state.auth_store.authenticate(form.username, form.password)
    if user is None:
        raise HTTPException(status_code=401, detail="incorrect username or password", headers={"WWW-Authenticate": "Bearer"})
    request.app.state.audit_store.record(user.id, "auth.login", "user", user.id)
    return Token(access_token=create_access_token(user))


@router.get("/api/v1/auth/me", response_model=User)
def me(user: User = Depends(current_user)) -> User:
    return user


@router.get("/api/v1/audit", response_model=AuditResponse)
def audit(request: Request, limit: int = Query(default=100, ge=1, le=500), user: User = Depends(current_user)) -> AuditResponse:
    return AuditResponse(events=request.app.state.audit_store.list_for_user(user.id, limit))


@router.get("/api/v1/search", response_model=SearchResponse)
def search_records(
    request: Request,
    q: str = Query(min_length=1, max_length=300),
    record_id: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=20),
    user: User = Depends(current_user),
) -> SearchResponse:
    results = request.app.state.rag_index.search(q, record_id=record_id, limit=limit, owner_id=user.id if request.app.state.settings.auth_enabled else None)
    request.app.state.audit_store.record(user.id, "record.search", "record", record_id, metadata={"query_length": len(q), "result_count": len(results)})
    return SearchResponse(query=q, results=results)


@router.post("/api/v1/ask", response_model=AskResponse)
def ask_records(payload: AskRequest, request: Request, user: User = Depends(current_user)) -> AskResponse:
    conversations = request.app.state.conversation_store
    owner_id = user.id if request.app.state.settings.auth_enabled else "dev-user"
    conversation = conversations.create(owner_id) if not payload.conversation_id else conversations.get(payload.conversation_id, owner_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    conversation = conversations.append(conversation.id, "user", payload.question, owner_id=owner_id)
    history = [message.model_dump(mode="json") for message in conversation.messages]
    result = request.app.state.qa_graph.invoke({**payload.model_dump(), "history": history, "owner_id": owner_id if request.app.state.settings.auth_enabled else None})
    citation_ids = [item.citation_id for item in result.get("results", [])]
    conversations.append(conversation.id, "assistant", result["answer"], citation_ids, owner_id=owner_id)
    request.app.state.audit_store.record(user.id, "record.ask", "conversation", conversation.id, metadata={"question_length": len(payload.question), "citation_count": len(citation_ids)})
    return AskResponse(
        question=payload.question,
        answer=result["answer"],
        citations=result.get("results", []),
        mode=result["mode"],
        conversation_id=conversation.id,
        safety_level=result.get("safety_level", "normal"),
        safety_flags=result.get("safety_flags", []),
        evidence=result.get("evidence", {}),
    )


@router.get("/api/v1/timeline", response_model=TimelineResponse)
def timeline(request: Request, limit: int = Query(default=100, ge=1, le=500), user: User = Depends(current_user)) -> TimelineResponse:
    return request.app.state.timeline_service.build(limit, user.id if request.app.state.settings.auth_enabled else None)


@router.get("/api/v1/analytics", response_model=AnalyticsResponse)
def analytics(request: Request, user: User = Depends(current_user)) -> AnalyticsResponse:
    return request.app.state.analytics_service.analyze(user.id if request.app.state.settings.auth_enabled else None)


@router.get("/api/v1/literature/search", response_model=LiteratureSearchResponse)
def literature_search(
    request: Request,
    q: str = Query(min_length=3, max_length=300),
    limit: int = Query(default=5, ge=1, le=10),
    user: User = Depends(current_user),
) -> LiteratureSearchResponse:
    try:
        results = request.app.state.pubmed_client.search(q, limit)
    except LiteratureUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    request.app.state.audit_store.record(user.id, "literature.search", "literature", metadata={"query_length": len(q), "result_count": len(results)})
    return LiteratureSearchResponse(query=q, results=results)


@router.post("/api/v1/literature/ask", response_model=LiteratureAskResponse)
def literature_ask(payload: LiteratureAskRequest, request: Request, user: User = Depends(current_user)) -> LiteratureAskResponse:
    assessment = SafetyChecker().assess(payload.question)
    if assessment.level == "urgent":
        response = LiteratureAskResponse(question=payload.question, answer=assessment.message or "Please seek immediate help.", citations=[], mode="safety")
        request.app.state.audit_store.record(user.id, "literature.ask", "literature", success=True, metadata={"safety": "urgent"})
        return response
    try:
        results = request.app.state.pubmed_client.search(payload.question, payload.limit)
    except LiteratureUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    answer, mode = request.app.state.literature_answerer.answer(payload.question, results, source_label="medical literature")
    request.app.state.audit_store.record(user.id, "literature.ask", "literature", metadata={"question_length": len(payload.question), "result_count": len(results)})
    return LiteratureAskResponse(question=payload.question, answer=answer, citations=results, mode=mode)


@router.get("/api/v1/records", response_model=RecordListResponse)
def list_records(request: Request, user: User = Depends(current_user)) -> RecordListResponse:
    items = get_store(request).list_records(user.id if request.app.state.settings.auth_enabled else None)
    return RecordListResponse(items=items, total=len(items))


@router.get("/api/v1/records/{record_id}", response_model=RecordDetail)
def get_record(record_id: str, request: Request, user: User = Depends(current_user)) -> RecordDetail:
    try:
        record = get_store(request).get_record(record_id, user.id if request.app.state.settings.auth_enabled else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    return record


@router.post("/api/v1/records", response_model=RecordDetail, status_code=status.HTTP_201_CREATED)
async def create_record(
    request: Request,
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
    user: User = Depends(current_user),
) -> RecordDetail:
    del description
    store = get_store(request)
    try:
        owner_id = user.id if request.app.state.settings.auth_enabled else "dev-user"
        summary = await store.save_upload(file, owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    result = request.app.state.ingestion_graph.invoke(
        {
            "record_id": summary.id,
            "source_path": str(store.raw_path(summary.id)),
            "source_type": summary.source_type,
        }
    )
    if result.get("error"):
        return store.set_failed(summary.id, result["error"])
    store.set_extracted(summary.id, result["text"])
    from backend.app.models.clinical import NormalizedDocument

    response = store.set_structured(summary.id, NormalizedDocument.model_validate(result["structured"]), owner_id)
    request.app.state.rag_index.index_record(
        summary.id,
        summary.filename,
        result["text"],
        owner_id,
        document_date=response.structured.document_date.isoformat() if response.structured and response.structured.document_date else None,
        document_type=response.structured.document_type if response.structured else None,
    )
    request.app.state.audit_store.record(user.id, "record.upload", "record", summary.id, metadata={"size_bytes": summary.size_bytes, "status": response.status})
    return response
