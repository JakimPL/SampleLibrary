from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection

from samplecore.models.module import Module
from samplecore.models.note_extraction import ModuleNoteExtraction
from samplecore.storage.repositories.note_extraction import PostgresModuleNoteExtractionRepository


def test_a_marked_module_is_reported_as_extracted(connection: Connection, stored_module: Module) -> None:
    repository = PostgresModuleNoteExtractionRepository(connection)

    repository.mark(ModuleNoteExtraction(module_id=stored_module.id, extracted_at=datetime.now(UTC)))

    assert repository.extracted_module_ids() == frozenset({stored_module.id})


def test_extracted_module_ids_on_an_untouched_catalog_returns_nothing(connection: Connection) -> None:
    assert PostgresModuleNoteExtractionRepository(connection).extracted_module_ids() == frozenset()


def test_extracted_module_ids_covers_every_marked_module(
    connection: Connection, stored_module: Module, stored_module_b: Module
) -> None:
    repository = PostgresModuleNoteExtractionRepository(connection)
    extracted_at = datetime.now(UTC)
    repository.mark(ModuleNoteExtraction(module_id=stored_module.id, extracted_at=extracted_at))
    repository.mark(ModuleNoteExtraction(module_id=stored_module_b.id, extracted_at=extracted_at))

    assert repository.extracted_module_ids() == frozenset({stored_module.id, stored_module_b.id})


def test_delete_for_module_leaves_every_other_mark_standing(
    connection: Connection, stored_module: Module, stored_module_b: Module
) -> None:
    repository = PostgresModuleNoteExtractionRepository(connection)
    extracted_at = datetime.now(UTC)
    repository.mark(ModuleNoteExtraction(module_id=stored_module.id, extracted_at=extracted_at))
    repository.mark(ModuleNoteExtraction(module_id=stored_module_b.id, extracted_at=extracted_at))

    repository.delete_for_module(stored_module.id)

    assert repository.extracted_module_ids() == frozenset({stored_module_b.id})
