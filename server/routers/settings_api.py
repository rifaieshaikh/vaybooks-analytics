"""Application settings routes."""

from fastapi import APIRouter, Depends, HTTPException

from server.account_aliases import get_aliases, migrate_account, remove_alias
from server.entities import list_open_reviews, merge_review, reject_review
from server.auth import assert_perm, require_user, type_perm
from server.customers import add_party_type, delete_party_type, get_settlement_settings, list_party_types, save_settlement_settings
from server.due_days import get_due_days_settings, save_default_due_days
from server.order_check import get_order_check_settings, save_default_policy
from server.org_policy import get_expense_categories, get_org_policy, save_expense_categories, save_org_policy
from server.schemas import (
    AccountAliasBody,
    EntityReviewBody,
    ActivityKindBody,
    DueDaysBody,
    ExpenseCategoriesBody,
    OrderCheckPolicyBody,
    OrgPolicyBody,
    SettlementBody,
)
from server.store import get_store

router = APIRouter()


@router.get("/api/settings/party-types")
def api_list_party_types(user=Depends(require_user)):
    assert_perm(user, "settings.advanced", type_perm("party", "view"))
    return {"types": list_party_types(get_store())}


@router.post("/api/settings/party-types")
def api_add_party_type(body: ActivityKindBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    try:
        return {"types": add_party_type(get_store(), body.label)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/api/settings/party-types/{type_uk}")
def api_delete_party_type(type_uk: str, user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    try:
        types = delete_party_type(get_store(), type_uk)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if types is None:
        raise HTTPException(404, "Not found")
    return {"types": types}


@router.get("/api/settings/settlement")
def api_get_settlement(user=Depends(require_user)):
    assert_perm(user, "settings.advanced", "customers.view")
    return get_settlement_settings(get_store())


@router.post("/api/settings/settlement")
def api_set_settlement(body: SettlementBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    try:
        return save_settlement_settings(
            get_store(), mode=body.mode, aging_bands=body.aging_bands, setup_complete=body.setup_complete,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/settings/due-days")
def api_get_due_days(user=Depends(require_user)):
    assert_perm(user, "settings.advanced", "customer.view")
    return get_due_days_settings(get_store())


@router.post("/api/settings/due-days")
def api_set_due_days(body: DueDaysBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    if body.due_days is None:
        raise HTTPException(400, "due_days required")
    return save_default_due_days(get_store(), body.due_days)


@router.get("/api/settings/order-check")
def api_get_order_check(user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    return get_order_check_settings(get_store())


@router.post("/api/settings/order-check")
def api_set_order_check(body: OrderCheckPolicyBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    return save_default_policy(get_store(), body.policy or {})


@router.get("/api/settings/org-policy")
def api_get_org_policy(user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    return get_org_policy(get_store())


@router.post("/api/settings/org-policy")
def api_set_org_policy(body: OrgPolicyBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    try:
        store = get_store()
        before = get_org_policy(store)
        saved = save_org_policy(store, body.model_dump())
        if saved.get("wholesale_pack") and not before.get("wholesale_pack"):
            from server.saved_reports import adopt_pack
            adopt_pack(store, user.get("username") or "")
        if saved.get("retail_pack") and not before.get("retail_pack"):
            from server.saved_reports import adopt_retail_pack
            adopt_retail_pack(store, user.get("username") or "")
        return saved
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/settings/expense-categories")
def api_get_expense_categories(user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    return get_expense_categories(get_store())


@router.post("/api/settings/expense-categories")
def api_set_expense_categories(body: ExpenseCategoriesBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    return save_expense_categories(get_store(), body.categories or {}, pack=body.pack)


@router.get("/api/settings/account-aliases")
def api_list_account_aliases(user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    return get_aliases(get_store())


@router.post("/api/settings/account-aliases/migrate")
def api_migrate_account(body: AccountAliasBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    try:
        return migrate_account(get_store(), body.source, body.destination)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/api/settings/account-aliases")
def api_remove_account_alias(source: str = "", user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    try:
        return remove_alias(get_store(), source)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/settings/entity-review")
def api_list_entity_review(user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    return list_open_reviews(get_store())


@router.post("/api/settings/entity-review/merge")
def api_merge_entity_review(body: EntityReviewBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    try:
        return merge_review(get_store(), body.kind, body.left_name, body.right_entity_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/settings/entity-review/reject")
def api_reject_entity_review(body: EntityReviewBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    try:
        return reject_review(get_store(), body.kind, body.left_name, body.right_entity_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
