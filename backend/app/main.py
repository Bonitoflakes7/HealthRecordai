from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router
from backend.app.core.config import settings
from backend.app.services.records import RecordStore
from backend.app.services.extraction import DocumentExtractor
from backend.app.services.normalization import DocumentNormalizer
from backend.app.workflows.ingestion import build_ingestion_graph
from backend.app.services.retrieval import LocalRecordIndex
from backend.app.services.answering import configured_answerer
from backend.app.workflows.qa import build_qa_graph
from backend.app.services.sqlite_conversations import SqliteConversationStore
from backend.app.services.timeline import TimelineService
from backend.app.services.analytics import ClinicalAnalyticsService
from backend.app.services.pubmed import PubMedClient
from backend.app.services.security import AuthStore, AuditStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auth_enabled and len(settings.auth_secret_key.encode("utf-8")) < 32:
        raise RuntimeError("AUTH_SECRET_KEY must be at least 32 bytes when AUTH_ENABLED=true")
    app.state.settings = settings
    app.state.record_store = RecordStore()
    app.state.conversation_store = SqliteConversationStore(settings.conversation_db_path or settings.data_dir / "health_record.db")
    database_path = settings.conversation_db_path or settings.data_dir / "health_record.db"
    app.state.auth_store = AuthStore(database_path)
    app.state.audit_store = AuditStore(database_path)
    app.state.ingestion_graph = build_ingestion_graph(DocumentExtractor(), DocumentNormalizer())
    app.state.rag_index = LocalRecordIndex()
    for summary in app.state.record_store.list_records():
        detail = app.state.record_store.get_record(summary.id)
        if detail and detail.text:
            app.state.rag_index.index_record(
                summary.id,
                summary.filename,
                detail.text,
                summary.owner_id or "dev-user",
                document_date=detail.structured.document_date.isoformat() if detail.structured and detail.structured.document_date else None,
                document_type=detail.structured.document_type if detail.structured else None,
            )
    app.state.qa_graph = build_qa_graph(app.state.rag_index, configured_answerer())
    app.state.timeline_service = TimelineService(app.state.record_store)
    app.state.analytics_service = ClinicalAnalyticsService(app.state.record_store)
    app.state.pubmed_client = PubMedClient(settings.data_dir / "literature", settings.pubmed_email)
    app.state.literature_answerer = configured_answerer()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
