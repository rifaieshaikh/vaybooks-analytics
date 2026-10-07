"""Mapper and imported-data maintenance routes."""

from fastapi import APIRouter, Depends, HTTPException

from server.auth import assert_perm, require_user, type_perm
from server.cleanup import cleanup_imported_data, factory_reset
from server.mappers import PRESETS, preset_by_id, validate_mapper
from server.rebuild import rebuild_type
from server.schemas import CleanupBody, MapperBody
from server.settings import SALES_SAME_AMOUNT_UK, SOURCE_TYPES
from server.store import get_store

router = APIRouter()


@router.get("/api/mappers")
def list_mappers(user=Depends(require_user)):
    rows = []
    for doc in get_store().list_mappers():
        type_name = doc.get("type")
        if type_perm(type_name, "view") in user["permissions"] or type_perm(type_name, "map") in user["permissions"]:
            rows.append(doc)
    return {"mappers": rows}


@router.get("/api/mappers/presets")
def list_presets(user=Depends(require_user)):
    from server.pilots import presets_for_received_pilots, samples_root
    return {"presets": list(PRESETS) + presets_for_received_pilots(samples_root())}


@router.post("/api/mappers/{type_name}/preset/{preset_id}")
def apply_preset(type_name: str, preset_id: str, user=Depends(require_user)):
    if type_name not in SOURCE_TYPES:
        raise HTTPException(400, "Unknown type")
    assert_perm(user, type_perm(type_name, "map"))
    preset = preset_by_id(preset_id)
    if not preset or preset.get("type") != type_name:
        raise HTTPException(404, "Preset not found")
    payload = {
        "column_map": dict(preset.get("column_map") or {}),
        "unique_key": list(preset.get("unique_key") or []),
        "extra_types": {},
    }
    prior_mode = (get_store().get_mapper(type_name) or {}).get("event_mode")
    if prior_mode:
        payload["event_mode"] = prior_mode
    err = validate_mapper(type_name, payload)
    if err:
        raise HTTPException(400, err)
    saved = get_store().put_mapper(type_name, payload)
    saved["preset_id"] = preset_id
    if preset.get("shape"):
        saved["shape"] = preset["shape"]
    return saved


@router.get("/api/mappers/{type_name}")
def get_mapper(type_name: str, user=Depends(require_user)):
    if type_name not in SOURCE_TYPES:
        raise HTTPException(400, "Unknown type")
    assert_perm(user, type_perm(type_name, "view"), type_perm(type_name, "map"))
    doc = get_store().get_mapper(type_name)
    return doc or {"type": type_name, "column_map": {}, "unique_key": [], "extra_types": {}}


@router.put("/api/mappers/{type_name}")
def put_mapper(type_name: str, body: MapperBody, user=Depends(require_user)):
    if type_name not in SOURCE_TYPES:
        raise HTTPException(400, "Unknown type")
    assert_perm(user, type_perm(type_name, "map"))
    payload = body.model_dump()
    prior_mode = (get_store().get_mapper(type_name) or {}).get("event_mode")
    if prior_mode:
        payload["event_mode"] = prior_mode
    err = validate_mapper(type_name, payload)
    if err:
        raise HTTPException(400, err)
    warning = ""
    if type_name == "sales" and set(payload.get("unique_key") or []) == SALES_SAME_AMOUNT_UK:
        warning = "same customer + date + amount counts as one sale."
    saved = get_store().put_mapper(type_name, payload)
    saved["warning"] = warning
    return saved


@router.post("/api/mappers/{type_name}/rebuild-uk")
def rebuild_uk(type_name: str, user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    store = get_store()
    mapper = store.get_mapper(type_name)
    if not mapper or not mapper.get("unique_key"):
        raise HTTPException(400, "Mapper unique_key is required")
    return rebuild_type(store, type_name, mapper)


@router.post("/api/data/cleanup")
def cleanup_data(body: CleanupBody | None = None, user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    return cleanup_imported_data(get_store(), body.types if body else None)


@router.post("/api/data/factory-reset")
def api_factory_reset(user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    return factory_reset(get_store())
