"""Request models shared by the API routers."""

from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    username: str = ""
    password: str = ""


class ChangePasswordBody(BaseModel):
    current_password: str = ""
    new_password: str = ""


class MapperBody(BaseModel):
    column_map: dict = Field(default_factory=dict)
    unique_key: list[str] = Field(default_factory=list)
    extra_types: dict = Field(default_factory=dict)


class RunBody(BaseModel):
    packs: dict = Field(default_factory=dict)
    report_date: str = ""
    reports: list[str] = Field(default_factory=list)
    from_run: str = ""


class ExportPdfBody(BaseModel):
    ids: list[str] = Field(default_factory=list)


class ActivityKindBody(BaseModel):
    label: str = ""


class SettlementBody(BaseModel):
    mode: str = "oldest"
    aging_bands: list | None = None
    setup_complete: bool = True


class DueDaysBody(BaseModel):
    due_days: int | None = 30


class DueDaysOverrideBody(BaseModel):
    due_days: int | None = None


class OrderCheckPolicyBody(BaseModel):
    policy: dict = Field(default_factory=dict)


class OrgPolicyBody(BaseModel):
    fiscal_year_start_month: int | None = 4
    timezone: str | None = "Asia/Kolkata"
    currency_code: str | None = "INR"
    currency_symbol: str | None = "₹"
    sales_tax_inclusive_rate: float | None = 0.18
    ar_balance_tolerance: float | None = None
    expense_pack: str | None = "vay_wholesale"
    terminology: dict = Field(default_factory=dict)
    targets: dict | None = None
    thresholds: dict | None = None
    weekly_run: bool | None = None
    last_weekly_report_date: str | None = None
    wholesale_pack: bool | None = None
    retail_pack: bool | None = None
    custom_columns: list | None = None


class AccountAliasBody(BaseModel):
    source: str = ""
    destination: str = ""


class EntityReviewBody(BaseModel):
    kind: str = "customer"
    left_name: str = ""
    right_entity_id: str = ""


class ExpenseCategoriesBody(BaseModel):
    categories: dict = Field(default_factory=dict)
    pack: str | None = "vay_wholesale"


class OrderCheckOverrideBody(BaseModel):
    policy: dict | None = None
    clear: bool = False


class OrderCheckFlagsBody(BaseModel):
    premium: bool | None = None
    blacklisted: bool | None = None


class OrderCheckRunBody(BaseModel):
    order_value: float | None = None
    order_qty: float | None = None


class ItemHoldingBody(BaseModel):
    min_hold: float | None = None
    fill_to: float | None = None
    clear_fill: bool = False
    lead_days: int | None = None
    review_days: int | None = None
    safety_stock: float | None = None
    max_days_hold: int | None = None
    clear_max_days: bool = False
    discontinued: bool | None = None


class ItemHoldingDefaultBody(BaseModel):
    min_hold: float | None = None
    max_days_hold: int | None = None


class PartyPatchBody(BaseModel):
    party_type: str = ""


class UserCreateBody(BaseModel):
    username: str = ""
    password: str = ""
    role: str = "Viewer"


class UserPatchBody(BaseModel):
    role: str | None = None
    enabled: bool | None = None
    password: str | None = None
    sales_reps: list[str] | None = None


class RoleBody(BaseModel):
    permissions: list[str] = Field(default_factory=list)


class RoleCreateBody(BaseModel):
    name: str = ""
    permissions: list[str] = Field(default_factory=list)


class CleanupBody(BaseModel):
    types: list[str] | None = None


class SavedViewBody(BaseModel):
    page: str = ""
    filters: dict = Field(default_factory=dict)


class ActionBody(BaseModel):
    action_type: str = ""
    subject_name: str = ""
    subject_kind: str = ""
    proposal: str = ""
    owner: str = ""
    due_date: str = ""
    amount: float | None = None
    report_date: str = ""
    quality_message: str = ""
    was_inactive: bool = False
    assigned_at: str = ""


class ActionStatusBody(BaseModel):
    status: str = ""


class CollectionContactBody(BaseModel):
    customer_name: str = ""
    action_id: str = ""
    contacted_on: str = ""
    staff: str = ""
    channel: str = ""
    note: str = ""
    next_step: str = ""
    next_follow_up: str = ""


class CollectionPromiseBody(BaseModel):
    customer_name: str = ""
    action_id: str = ""
    amount: float | None = None
    promised_on: str = ""
    invoice_refs: list | str = ""


class CollectionDisputeBody(BaseModel):
    customer_name: str = ""
    promise_id: str = ""
    invoice_refs: list | str = ""
    note: str = ""
    status: str = ""
    opened_on: str = ""


class CollectionAllocationBody(BaseModel):
    promise_id: str = ""
    source_uk: str = ""
    source_type: str = "receipt"
    amount: float | None = None


class AskBody(BaseModel):
    text: str = ""
    report_date: str = ""


class SavedReportBody(BaseModel):
    name: str = ""
    metric_ids: list[str] = Field(default_factory=list)
    dimension: str = "customer"
    filters: list = Field(default_factory=list)
    comparison: str = "current"
    schedule: bool = False
    custom_column: str = ""
    show_pack_size: bool = False
    row_filter: str = ""
    report_date: str = ""
    template_id: str = ""


class ReorderBody(BaseModel):
    budget: float | None = None
    lines: list = Field(default_factory=list)
    assign: bool = False
    owner: str = ""
    report_date: str = ""
