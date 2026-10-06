"""Industry / pilot packs."""

from vay.packs.retail import EXPENSE_ACCOUNT_MAP as RETAIL_EXPENSE_ACCOUNT_MAP
from vay.packs.retail import PACK_ID as RETAIL_PACK_ID
from vay.packs.retail import PACK_LABEL as RETAIL_PACK_LABEL
from vay.packs.vay_wholesale import EXPENSE_ACCOUNT_MAP, PACK_ID, PACK_LABEL

PACKS = {
    PACK_ID: {
        "id": PACK_ID,
        "label": PACK_LABEL,
        "expense_account_map": EXPENSE_ACCOUNT_MAP,
    },
    RETAIL_PACK_ID: {
        "id": RETAIL_PACK_ID,
        "label": RETAIL_PACK_LABEL,
        "expense_account_map": RETAIL_EXPENSE_ACCOUNT_MAP,
    },
}

DEFAULT_EXPENSE_PACK = PACK_ID


def get_pack(pack_id=None):
    return PACKS.get(pack_id or DEFAULT_EXPENSE_PACK) or PACKS[DEFAULT_EXPENSE_PACK]


def default_expense_account_map():
    return {k: list(v) for k, v in get_pack().get("expense_account_map", {}).items()}
