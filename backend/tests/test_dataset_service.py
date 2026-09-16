"""Dataset validation and permission tests."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request, UploadFile

from model.dataset import (
    Dataset,
    DatasetUpdateRequest,
    normalize_dataset_tags,
    normalize_dataset_types,
)
from service.dataset_service import (
    DEFAULT_SHAREGPT_DATASET_ID,
    _require_owner,
    _require_visible,
    _serialize,
    _validate_jsonl,
    create_dataset_svc,
    download_dataset_svc,
    ensure_default_datasets,
    resolve_dataset_for_task,
)
from utils.error_handler import ErrorResponse


def test_normalize_dataset_types_supports_multi_select():
    assert normalize_dataset_types(["LLM", "mcp", "llm"]) == ["llm", "mcp"]


@pytest.mark.parametrize("types", [[], ["unknown"], ["llm", "bad"]])
def test_normalize_dataset_types_rejects_invalid_values(types):
    with pytest.raises(ValueError):
        normalize_dataset_types(types)


def test_normalize_dataset_tags_preserves_case_and_deduplicates():
    assert normalize_dataset_tags(["文本", "shareGPT", " sharegpt ", ""]) == [
        "文本",
        "shareGPT",
    ]


def test_dataset_update_rejects_blank_name():
    with pytest.raises(ValueError, match="Dataset name is required"):
        DatasetUpdateRequest(name="   ")


def test_validate_jsonl_counts_non_empty_object_rows(tmp_path):
    dataset = tmp_path / "valid.jsonl"
    dataset.write_text('{"prompt":"one"}\n\n{"prompt":"two"}\n', encoding="utf-8")
    assert _validate_jsonl(str(dataset)) == 2


@pytest.mark.parametrize("content", ['{"ok": true}\nnot-json\n', "[1, 2]\n", "\n"])
def test_validate_jsonl_rejects_invalid_content(tmp_path, content):
    dataset = tmp_path / "invalid.jsonl"
    dataset.write_text(content, encoding="utf-8")
    with pytest.raises(ErrorResponse) as exc:
        _validate_jsonl(str(dataset))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_dataset_rejects_json_files():
    request = MagicMock(spec=Request)
    file = UploadFile(filename="sharegpt.json", file=BytesIO(b"[]"))
    with pytest.raises(ErrorResponse) as exc:
        await create_dataset_svc(
            request,
            "ShareGPT",
            None,
            True,
            ["llm"],
            ["文本", "shareGPT"],
            file,
        )
    assert exc.value.status_code == 400


def test_private_dataset_is_hidden_from_non_owner():
    dataset = Dataset(created_by="alice", is_public=0)
    with pytest.raises(ErrorResponse) as exc:
        _require_visible(dataset, "bob")
    assert exc.value.status_code == 404


def test_public_dataset_is_visible_but_not_downloadable_by_non_owner():
    dataset = Dataset(created_by="alice", is_public=1)
    _require_visible(dataset, "bob")
    with pytest.raises(ErrorResponse) as exc:
        _require_owner(dataset, "bob")
    assert exc.value.status_code == 403


def test_system_dataset_cannot_be_modified_or_deleted():
    dataset = Dataset(
        id=DEFAULT_SHAREGPT_DATASET_ID,
        created_by="system",
        is_public=1,
    )
    with pytest.raises(ErrorResponse) as exc:
        _require_owner(dataset, "system")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@patch("service.dataset_service._get_dataset", new_callable=AsyncMock)
@patch("service.dataset_service._username", return_value="alice")
async def test_system_dataset_cannot_be_downloaded(_mock_username, mock_get_dataset):
    mock_get_dataset.return_value = Dataset(
        id=DEFAULT_SHAREGPT_DATASET_ID,
        created_by="system",
        is_public=1,
        file_path="/uploads/system-sharegpt-v3-partial/ShareGPT_V3_partial.jsonl",
        file_name="ShareGPT_V3_partial.jsonl",
    )
    request = MagicMock(spec=Request)
    with pytest.raises(ErrorResponse) as exc:
        await download_dataset_svc(request, DEFAULT_SHAREGPT_DATASET_ID)
    assert exc.value.status_code == 403
    assert exc.value.payload["error"] == "System datasets cannot be downloaded"


def test_system_dataset_is_not_downloadable():
    dataset = Dataset(
        id=DEFAULT_SHAREGPT_DATASET_ID,
        name="ShareGPT V3 Partial",
        file_name="ShareGPT_V3_partial.jsonl",
        file_path="/uploads/system-sharegpt-v3-partial/ShareGPT_V3_partial.jsonl",
        file_size=10,
        record_count=1,
        dataset_types="llm",
        created_by="system",
        is_public=1,
    )
    serialized = _serialize(dataset, "system")
    assert serialized["is_system"] is True
    assert serialized["created_by"] == "-"
    assert serialized["can_download"] is False
    assert serialized["can_manage"] is False


def test_serialized_permissions_only_allow_creator_download():
    dataset = Dataset(
        id="dataset-1",
        name="shared",
        file_name="data.jsonl",
        file_path="/private/data.jsonl",
        file_size=10,
        record_count=1,
        dataset_types="llm,mcp",
        created_by="alice",
        is_public=1,
    )
    shared = _serialize(dataset, "bob")
    assert shared["can_download"] is False
    assert shared["can_manage"] is False
    assert "file_path" not in shared


@pytest.mark.asyncio
async def test_ensure_default_dataset_is_idempotently_mounted(tmp_path, monkeypatch):
    source_dir = tmp_path / "data"
    upload_dir = tmp_path / "uploads"
    source_dir.mkdir()
    source = source_dir / "ShareGPT_V3_partial.jsonl"
    source.write_text('{"id":"1","prompt":"hello"}\n', encoding="utf-8")
    monkeypatch.setenv("DEFAULT_SHAREGPT_DATASET_PATH", str(source))
    monkeypatch.setattr("service.dataset_service.UPLOAD_FOLDER", str(upload_dir))
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    await ensure_default_datasets(db)
    await ensure_default_datasets(db)

    mounted = upload_dir / DEFAULT_SHAREGPT_DATASET_ID / "ShareGPT_V3_partial.jsonl"
    assert mounted.read_bytes() == source.read_bytes()
    assert db.execute.await_count == 2
    assert db.commit.await_count == 2


@pytest.mark.asyncio
@patch("service.dataset_service._username", return_value="bob")
async def test_resolve_dataset_rejects_private_non_owner(_mock_username, tmp_path):
    path = tmp_path / "private.jsonl"
    path.write_text('{"prompt":"secret"}\n', encoding="utf-8")
    dataset = Dataset(
        id="dataset-1",
        file_path=str(path),
        file_name=path.name,
        dataset_types="llm",
        created_by="alice",
        is_public=0,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = dataset
    request = MagicMock(spec=Request)
    request.state.db.execute = AsyncMock(return_value=result)

    with pytest.raises(ErrorResponse) as exc:
        await resolve_dataset_for_task(request, "dataset-1", "llm", "task-1")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@patch("service.dataset_service.validate_upload_path")
@patch("service.dataset_service._username", return_value="bob")
async def test_resolve_public_dataset_checks_task_type(
    _mock_username, _mock_validate_path, tmp_path
):
    path = tmp_path / "shared.jsonl"
    path.write_text('{"prompt":"hello"}\n', encoding="utf-8")
    dataset = Dataset(
        id="dataset-1",
        file_path=str(path),
        file_name=path.name,
        dataset_types="mcp",
        created_by="alice",
        is_public=1,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = dataset
    request = MagicMock(spec=Request)
    request.state.db.execute = AsyncMock(return_value=result)

    with pytest.raises(ErrorResponse) as exc:
        await resolve_dataset_for_task(request, "dataset-1", "llm", "task-1")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
@patch("service.dataset_service._copy_dataset_for_task", new_callable=AsyncMock)
@patch("service.dataset_service.validate_upload_path")
@patch("service.dataset_service._username", return_value="bob")
async def test_resolve_public_dataset_creates_task_owned_copy(
    _mock_username, _mock_validate_path, mock_copy, tmp_path
):
    path = tmp_path / "shared.jsonl"
    path.write_text('{"prompt":"hello"}\n', encoding="utf-8")
    dataset = Dataset(
        id="dataset-1",
        file_path=str(path),
        file_name=path.name,
        dataset_types="llm,mcp",
        created_by="alice",
        is_public=1,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = dataset
    request = MagicMock(spec=Request)
    request.state.db.execute = AsyncMock(return_value=result)
    mock_copy.return_value = "/uploads/task-1/shared.jsonl"

    resolved = await resolve_dataset_for_task(request, "dataset-1", "llm", "task-1")

    assert resolved == "/uploads/task-1/shared.jsonl"
    mock_copy.assert_awaited_once_with(dataset, str(path), "task-1")
