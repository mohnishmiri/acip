from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.models import (
    Application,
    ApplicationMapping,
    AuditLog,
    AzureSubscription,
    Environment,
    ResourceTagMapping,
    Role,
    ServiceCategoryRule,
    User,
    UserRoleAssignment,
)
from app.schemas.common import (
    ApplicationIn,
    AppMappingIn,
    CategoryRuleIn,
    Envelope,
    RoleAssignmentIn,
    SettingUpdate,
    SubscriptionIn,
    SubscriptionPatch,
    TagMappingIn,
)
from app.security.auth import CurrentUser, require
from app.services import audit_service, job_service, settings_service, subscription_service

router = APIRouter(prefix="/admin", tags=["Administration & Settings"])


# ----------------------------------------------------------------------- subscriptions
@router.get("/subscriptions")
def list_subscriptions(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return [subscription_service.serialize(s) for s in db.execute(select(AzureSubscription).order_by(AzureSubscription.id)).scalars()
            if user.allowed_subscription_fks is None or s.id in user.allowed_subscription_fks]


@router.post("/subscriptions", status_code=201, summary="Register a subscription (no code change required)")
def create_subscription(body: SubscriptionIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    if db.execute(select(AzureSubscription).where(AzureSubscription.subscription_id == body.subscription_id.lower())).first():
        raise ConflictError("Subscription already registered")
    sub = subscription_service.upsert_subscription(db, body.model_dump())
    audit_service.record(db, user, "subscription.create", entity_type="subscription", entity_id=sub.subscription_id, details={"name": sub.subscription_name}, request=request)
    db.commit()
    return subscription_service.serialize(sub)


@router.put("/subscriptions/{subscription_id}")
def update_subscription(subscription_id: str, body: SubscriptionPatch, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    sub = subscription_service.get_subscription(db, subscription_id)
    data: dict[str, Any] = subscription_service.serialize(sub)
    patch = body.model_dump(exclude_unset=True)
    merged = {"subscription_id": sub.subscription_id, "subscription_name": data["subscription_name"], "application_id": sub.application_id,
              "environment": data["environment"], "tenant_id": sub.tenant_id, "billing_currency": sub.billing_currency, "enabled": sub.enabled,
              "is_demo": sub.is_demo, **patch}
    if "exports" not in patch:
        merged.pop("exports", None)
    sub = subscription_service.upsert_subscription(db, merged)
    audit_service.record(db, user, "subscription.update", entity_type="subscription", entity_id=sub.subscription_id, details={k: str(v) for k, v in patch.items()}, request=request)
    db.commit()
    return subscription_service.serialize(sub)


@router.delete("/subscriptions/{subscription_id}", status_code=204)
def delete_subscription(subscription_id: str, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    subscription_service.delete_subscription(db, subscription_id)
    audit_service.record(db, user, "subscription.delete", entity_type="subscription", entity_id=subscription_id, request=request)
    db.commit()


# ------------------------------------------------------------------------ applications
@router.get("/applications")
def list_applications(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    counts = dict(db.execute(select(AzureSubscription.application_id, func.count()).group_by(AzureSubscription.application_id)).all())
    return [{"id": a.id, "code": a.code, "name": a.name, "description": a.description, "owner": a.owner, "is_active": a.is_active,
             "sort_order": a.sort_order, "is_demo": a.is_demo, "subscription_count": counts.get(a.id, 0)}
            for a in db.execute(select(Application).order_by(Application.sort_order, Application.name)).scalars()]


@router.post("/applications", status_code=201)
def create_application(body: ApplicationIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    if db.execute(select(Application).where(Application.code == body.code)).first():
        raise ConflictError("Application code already exists")
    a = Application(**body.model_dump())
    db.add(a)
    db.flush()
    audit_service.record(db, user, "application.create", entity_type="application", entity_id=str(a.id), details=body.model_dump(), request=request)
    db.commit()
    return {"id": a.id}


@router.put("/applications/{application_id}")
def update_application(application_id: int, body: ApplicationIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    a = db.get(Application, application_id)
    if a is None:
        raise NotFoundError("Application not found")
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    audit_service.record(db, user, "application.update", entity_type="application", entity_id=str(a.id), details=body.model_dump(), request=request)
    db.commit()
    return {"id": a.id}


@router.delete("/applications/{application_id}", status_code=204, summary="Delete an application (only when nothing references it)")
def delete_application(application_id: int, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    from app.models import Budget

    a = db.get(Application, application_id)
    if a is None:
        raise NotFoundError("Application not found")
    subs = db.execute(select(func.count()).select_from(AzureSubscription).where(AzureSubscription.application_id == application_id)).scalar_one()
    budgets = db.execute(select(func.count()).select_from(Budget).where(Budget.scope_type == "application", Budget.scope_ref == str(application_id))).scalar_one()
    data = db.execute(text("SELECT 1 FROM daily_cost_aggregates WHERE application_id = :a LIMIT 1"), {"a": application_id}).first()
    if subs or budgets or data:
        raise ConflictError(f"Application is still referenced ({subs} subscription(s), {budgets} budget(s){', billing history' if data else ''}); reassign or set it inactive instead.")
    db.delete(a)
    audit_service.record(db, user, "application.delete", entity_type="application", entity_id=str(application_id), request=request)
    db.commit()


# ------------------------------------------------------------------- allocation rules
def _reattribute_hint() -> str:
    return "Rule changes apply to newly ingested data. Run 'Re-apply allocation rules' to update stored history."


@router.get("/tag-mappings")
def list_tag_mappings(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return [{"id": t.id, "tag_key": t.tag_key, "tag_value": t.tag_value, "target_dimension": t.target_dimension, "target_value": t.target_value,
             "priority": t.priority, "enabled": t.enabled, "description": t.description}
            for t in db.execute(select(ResourceTagMapping).order_by(ResourceTagMapping.target_dimension, ResourceTagMapping.priority)).scalars()]


@router.post("/tag-mappings", status_code=201)
def create_tag_mapping(body: TagMappingIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    t = ResourceTagMapping(**body.model_dump())
    db.add(t)
    db.flush()
    audit_service.record(db, user, "tag_mapping.create", entity_type="tag_mapping", entity_id=str(t.id), details=body.model_dump(), request=request)
    db.commit()
    return {"id": t.id, "note": _reattribute_hint()}


@router.put("/tag-mappings/{mapping_id}")
def update_tag_mapping(mapping_id: int, body: TagMappingIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    t = db.get(ResourceTagMapping, mapping_id)
    if t is None:
        raise NotFoundError("Mapping not found")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    audit_service.record(db, user, "tag_mapping.update", entity_type="tag_mapping", entity_id=str(t.id), details=body.model_dump(), request=request)
    db.commit()
    return {"id": t.id, "note": _reattribute_hint()}


@router.delete("/tag-mappings/{mapping_id}", status_code=204)
def delete_tag_mapping(mapping_id: int, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    t = db.get(ResourceTagMapping, mapping_id)
    if t is None:
        raise NotFoundError("Mapping not found")
    db.delete(t)
    audit_service.record(db, user, "tag_mapping.delete", entity_type="tag_mapping", entity_id=str(mapping_id), request=request)
    db.commit()


@router.get("/application-mappings")
def list_app_mappings(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    envs = {e.id: e.code for e in db.execute(select(Environment)).scalars()}
    subs = {s.id: s.subscription_id for s in db.execute(select(AzureSubscription)).scalars()}
    return [{"id": m.id, "match_type": m.match_type, "pattern": m.pattern, "subscription_id": subs.get(m.subscription_fk), "application_id": m.application_id,
             "environment": envs.get(m.environment_id), "allocation_status": m.allocation_status, "priority": m.priority, "enabled": m.enabled,
             "description": m.description}
            for m in db.execute(select(ApplicationMapping).order_by(ApplicationMapping.priority, ApplicationMapping.id)).scalars()]


def _mapping_values(db: Session, body: AppMappingIn) -> dict[str, Any]:
    data = body.model_dump()
    sub_guid = data.pop("subscription_id")
    env_code = data.pop("environment")
    data["subscription_fk"] = None
    if sub_guid:
        s = db.execute(select(AzureSubscription).where(AzureSubscription.subscription_id == sub_guid.lower())).scalar_one_or_none()
        if s is None:
            raise ValidationFailed("Unknown subscription")
        data["subscription_fk"] = s.id
    data["environment_id"] = None
    if env_code:
        e = db.execute(select(Environment).where(Environment.code == env_code)).scalar_one_or_none()
        if e is None:
            raise ValidationFailed("Unknown environment")
        data["environment_id"] = e.id
    if data.get("application_id") is not None and db.get(Application, data["application_id"]) is None:
        raise ValidationFailed("Unknown application")
    return data


@router.post("/application-mappings", status_code=201)
def create_app_mapping(body: AppMappingIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    m = ApplicationMapping(**_mapping_values(db, body))
    db.add(m)
    db.flush()
    audit_service.record(db, user, "application_mapping.create", entity_type="application_mapping", entity_id=str(m.id), details=body.model_dump(), request=request)
    db.commit()
    return {"id": m.id, "note": _reattribute_hint()}


@router.put("/application-mappings/{mapping_id}")
def update_app_mapping(mapping_id: int, body: AppMappingIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    m = db.get(ApplicationMapping, mapping_id)
    if m is None:
        raise NotFoundError("Mapping not found")
    for k, v in _mapping_values(db, body).items():
        setattr(m, k, v)
    audit_service.record(db, user, "application_mapping.update", entity_type="application_mapping", entity_id=str(m.id), details=body.model_dump(), request=request)
    db.commit()
    return {"id": m.id, "note": _reattribute_hint()}


@router.delete("/application-mappings/{mapping_id}", status_code=204)
def delete_app_mapping(mapping_id: int, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    m = db.get(ApplicationMapping, mapping_id)
    if m is None:
        raise NotFoundError("Mapping not found")
    db.delete(m)
    audit_service.record(db, user, "application_mapping.delete", entity_type="application_mapping", entity_id=str(mapping_id), request=request)
    db.commit()


@router.get("/category-rules")
def list_category_rules(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return [{"id": r.id, "match_field": r.match_field, "pattern": r.pattern, "category": r.category, "priority": r.priority, "enabled": r.enabled,
             "description": r.description} for r in db.execute(select(ServiceCategoryRule).order_by(ServiceCategoryRule.priority, ServiceCategoryRule.id)).scalars()]


@router.post("/category-rules", status_code=201)
def create_category_rule(body: CategoryRuleIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    r = ServiceCategoryRule(**body.model_dump())
    db.add(r)
    db.flush()
    audit_service.record(db, user, "category_rule.create", entity_type="category_rule", entity_id=str(r.id), details=body.model_dump(), request=request)
    db.commit()
    return {"id": r.id, "note": _reattribute_hint()}


@router.put("/category-rules/{rule_id}")
def update_category_rule(rule_id: int, body: CategoryRuleIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    r = db.get(ServiceCategoryRule, rule_id)
    if r is None:
        raise NotFoundError("Rule not found")
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    audit_service.record(db, user, "category_rule.update", entity_type="category_rule", entity_id=str(r.id), details=body.model_dump(), request=request)
    db.commit()
    return {"id": r.id, "note": _reattribute_hint()}


@router.delete("/category-rules/{rule_id}", status_code=204)
def delete_category_rule(rule_id: int, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    r = db.get(ServiceCategoryRule, rule_id)
    if r is None:
        raise NotFoundError("Rule not found")
    db.delete(r)
    audit_service.record(db, user, "category_rule.delete", entity_type="category_rule", entity_id=str(rule_id), request=request)
    db.commit()


@router.post("/reattribute", summary="Re-apply allocation and category rules to stored billing records (background job)")
def reattribute(request: Request, subscription_id: str | None = None, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    sub_fk = None
    if subscription_id:
        sub_fk = subscription_service.get_subscription(db, subscription_id).id
    job, created = job_service.enqueue_job(db, "reattribute", subscription_fk=sub_fk, priority=90, triggered_by=user.email or user.name)
    audit_service.record(db, user, "allocation.reattribute", entity_type="subscription", entity_id=subscription_id, request=request)
    db.commit()
    return {"job_id": job.id, "created": created}


# ---------------------------------------------------------------------------- settings
@router.get("/settings")
def get_settings_list(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    return settings_service.all_settings(db)


@router.put("/settings/{key}")
def update_setting(key: str, body: SettingUpdate, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    if key not in settings_service.DEFAULT_SETTINGS:
        raise NotFoundError(f"Unknown setting '{key}'")
    v = body.value
    default = settings_service.DEFAULT_SETTINGS[key][0]
    if isinstance(default, bool) and not isinstance(v, bool) or isinstance(default, (int, float)) and not isinstance(v, (int, float)):
        raise ValidationFailed(f"Setting '{key}' expects a {type(default).__name__}")
    if key == "reporting.week_start_isodow" and not (1 <= int(v) <= 7):
        raise ValidationFailed("week start must be 1 (Monday) … 7 (Sunday)")
    if key == "anomaly.sensitivity" and v not in ("low", "medium", "high"):
        raise ValidationFailed("sensitivity must be low, medium or high")
    if key == "forecast.default_method" and v not in ("run_rate", "recent", "trend"):
        raise ValidationFailed("method must be run_rate, recent or trend")
    if key == "reporting.default_cost_type" and v not in ("actual", "amortized"):
        raise ValidationFailed("cost type must be actual or amortized")
    if key == "attribution.precedence" and (not isinstance(v, list) or set(v) - {"resource_group_rule", "subscription", "resource_tag"}):
        raise ValidationFailed("precedence must be a list of resource_group_rule, subscription, resource_tag")
    settings_service.set_setting(db, key, v, user.email or user.name)
    audit_service.record(db, user, "setting.update", entity_type="setting", entity_id=key, details={"value": v}, request=request)
    db.commit()
    return {"key": key, "value": v}


# ------------------------------------------------------------------------ users & roles
@router.get("/roles")
def roles(db: Session = Depends(get_db), user: CurrentUser = Depends(require("read"))):
    from app.security.auth import PERMISSIONS

    return [{"code": r.code, "name": r.name, "description": r.description, "entra_app_role": r.entra_app_role, "permissions": sorted(PERMISSIONS.get(r.code, set()))}
            for r in db.execute(select(Role).order_by(Role.id)).scalars()]


@router.get("/users")
def users(db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    out = []
    for u in db.execute(select(User).order_by(User.display_name)).scalars():
        grants = db.execute(select(UserRoleAssignment, Role).join(Role, Role.id == UserRoleAssignment.role_id).where(UserRoleAssignment.user_id == u.id)).all()
        out.append({"id": u.id, "external_id": u.external_id, "email": u.email, "display_name": u.display_name, "is_active": u.is_active,
                    "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                    "assignments": [{"id": a.id, "role": r.code, "application_id": a.application_id} for a, r in grants]})
    return out


@router.post("/role-assignments", status_code=201, summary="Grant a role (optionally scoped to one application)")
def assign(body: RoleAssignmentIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    u = db.execute(select(User).where(User.external_id == body.external_id)).scalar_one_or_none()
    if u is None:
        u = User(external_id=body.external_id, email=body.email, display_name=body.display_name or body.email)
        db.add(u)
        db.flush()
    role = db.execute(select(Role).where(Role.code == body.role)).scalar_one()
    if body.application_id is not None and db.get(Application, body.application_id) is None:
        raise ValidationFailed("Unknown application")
    a = UserRoleAssignment(user_id=u.id, role_id=role.id, application_id=body.application_id, created_by=user.email or user.name)
    db.add(a)
    db.flush()
    audit_service.record(db, user, "role.assign", entity_type="user", entity_id=body.external_id, details=body.model_dump(), request=request)
    db.commit()
    return {"id": a.id}


@router.delete("/role-assignments/{assignment_id}", status_code=204)
def unassign(assignment_id: int, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    a = db.get(UserRoleAssignment, assignment_id)
    if a is None:
        raise NotFoundError("Assignment not found")
    db.delete(a)
    audit_service.record(db, user, "role.unassign", entity_type="role_assignment", entity_id=str(assignment_id), request=request)
    db.commit()


@router.get("/audit-logs", response_model=Envelope)
def audit_logs(page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), user: CurrentUser = Depends(require("admin"))):
    total = db.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    rows = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    return {"data": [{"id": r.id, "actor": r.actor, "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id, "details": r.details,
                      "ip_address": r.ip_address, "created_at": r.created_at.isoformat()} for r in rows],
            "meta": {"total": total, "page": page, "page_size": page_size}}
