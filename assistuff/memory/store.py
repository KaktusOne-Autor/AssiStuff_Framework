"""Per-profile memory aggregator."""

from __future__ import annotations

from pathlib import Path

from assistuff.config.schemas import MemoryConfig

from .dossier import Dossier, DossierCompiler, DossierSlicer, DossierStorage
from .long_term import LongTermMemory
from .retrieval import MemoryRetriever
from .short_term import ShortTermMemory
from .working import WorkingMemory


class MemoryStore:
    """Aggregates all memory layers for one profile."""

    def __init__(self, profile: str, profile_dir: Path, config: MemoryConfig) -> None:
        self.profile = profile
        self.profile_dir = Path(profile_dir)
        self.config = config

        self.short_term = ShortTermMemory(self.profile_dir / "memory.db")
        self.long_term = LongTermMemory(
            self.profile_dir / "memory.md",
            tags_config=config.long_term.tags,
        )
        tag_config = config.long_term.tags
        self.retriever = MemoryRetriever(
            self.long_term,
            max_retries=(
                tag_config.max_retries
                if tag_config.search_on_unknown_tag == "retry"
                else 0
            ),
        )
        self.dossier_storage = DossierStorage(self.profile_dir)
        self.dossier_slicer = DossierSlicer(config.dossier)

    def new_working(self, trace_id: str) -> WorkingMemory:
        return WorkingMemory(trace_id=trace_id)

    def load_dossier(self) -> Dossier:
        return self.dossier_storage.load(self.profile)

    def dossier_context(self, query: str) -> str:
        dossier = self.load_dossier()
        return self.dossier_slicer.slice(dossier, query)

    def make_compiler(self, roles) -> DossierCompiler:
        return DossierCompiler(
            config=self.config.dossier,
            roles=roles,
            short_term=self.short_term,
            long_term=self.long_term,
            storage=self.dossier_storage,
            profile=self.profile,
        )