"""App settings 服务：有效配置（Settings + app_settings 覆盖）、掩码视图、PATCH 持久化。

敏感值（api key/smtp 密码）只存 env 引用，绝不入库；API 返回掩码（8_SECURITY §5）。
PATCH 写审计（脱敏差异）。
"""

import re
from typing import Any

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.errors import DomainError
from wws_adviser.modules.appsettings import repository
from wws_adviser.modules.audit import service as audit_service


class SettingsValidationError(DomainError):
    code = "VALIDATION_ERROR"
    status = 422
    title = "设置校验失败"


# —— 自选（watchlist）：非敏感可调项，存 app_settings KV（技术债清理：PORT 自选 Tab）——

_WATCHLIST_KEY = "watchlist.codes"

_CODE_RE = re.compile(r"^\d{6}$")  # A股/场内ETF 6 位数字代码


def get_watchlist(db: DBSession) -> list[str]:
    """当前自选代码列表（保持用户排序，去重）。"""
    value = repository.get_value(db, _WATCHLIST_KEY)
    if not isinstance(value, list):
        return []
    return [str(c) for c in value]


def set_watchlist(
    db: DBSession,
    *,
    user_id: str,
    codes: list[str],
    request_id: str | None = None,
) -> list[str]:
    """整体替换自选（PUT 语义）。校验 6 位代码、保序去重；写审计。"""
    cleaned: list[str] = []
    for raw in codes:
        code = str(raw).strip()
        if not _CODE_RE.match(code):
            raise SettingsValidationError(f"非法标的代码: {raw}")
        if code not in cleaned:
            cleaned.append(code)
    repository.set_value(db, _WATCHLIST_KEY, cleaned)
    audit_service.append_event(
        db,
        action="watchlist_updated",
        actor=user_id,
        target_type="settings",
        target_id="watchlist",
        after={"count": len(cleaned)},
        request_id=request_id,
    )
    db.commit()
    return cleaned

# 各 section 允许 PATCH 的字段（白名单；敏感字段不在其中）
_PATCHABLE: dict[str, set[str]] = {
    "risk": {"single_cap", "industry_cap", "cash_floor", "top_n", "top_n_concentration"},
    "models": {"model_name", "model_base_url", "temperature", "max_tokens", "timeout", "retry"},
    "notifications": {"smtp_host", "smtp_port", "smtp_user", "from_addr", "to_addr", "use_tls",
                      "privacy_mode"},
}

# Settings 字段名映射（section 字段 → Settings 属性）
_FIELD_TO_SETTING: dict[str, str] = {
    "single_cap": "risk_single_cap",
    "industry_cap": "risk_industry_cap",
    "cash_floor": "risk_cash_floor",
    "top_n": "risk_top_n",
    "top_n_concentration": "risk_top_n_concentration",
    "model_name": "model_name",
    "model_base_url": "model_base_url",
    "temperature": "model_temperature",
    "max_tokens": "model_max_tokens",
    "timeout": "model_timeout",
    "retry": "model_retry",
    "smtp_host": "smtp_host",
    "smtp_port": "smtp_port",
    "smtp_user": "smtp_user",
    "from_addr": "smtp_from_addr",
    "to_addr": "smtp_to_addr",
    "use_tls": "smtp_use_tls",
    "privacy_mode": "notification_privacy_mode",
}


def effective_settings(db: DBSession, settings: Settings) -> Settings:
    """Settings + app_settings 覆盖 → 有效配置（PATCH 实际生效路径）。"""
    stored = repository.all_settings(db)
    overrides: dict[str, Any] = {}
    for section, patch in stored.items():
        if not isinstance(patch, dict):
            continue
        for field in _PATCHABLE.get(section, set()):
            if field in patch:
                setting_key = _FIELD_TO_SETTING.get(field)
                if setting_key:
                    overrides[setting_key] = patch[field]
    if not overrides:
        return settings
    return settings.model_copy(update=overrides)


def masked_view(db: DBSession, settings: Settings, section: str) -> dict[str, Any]:
    """GET 视图：有效值 + 敏感项掩码（env 引用名，不含值）。"""
    eff = effective_settings(db, settings)
    if section == "risk":
        return {
            "single_cap": eff.risk_single_cap,
            "industry_cap": eff.risk_industry_cap,
            "cash_floor": eff.risk_cash_floor,
            "top_n": eff.risk_top_n,
            "top_n_concentration": eff.risk_top_n_concentration,
        }
    if section == "models":
        return {
            "source": eff.model_source,
            "base_url": eff.model_base_url,
            "model_name": eff.model_name,
            "temperature": eff.model_temperature,
            "max_tokens": eff.model_max_tokens,
            "timeout": eff.model_timeout,
            "retry": eff.model_retry,
            "api_key": f"已通过环境变量 {eff.model_api_key_ref} 配置（不回显）",
        }
    if section == "notifications":
        return {
            "source": eff.notifier_source,
            "smtp_host": eff.smtp_host,
            "smtp_port": eff.smtp_port,
            "smtp_user": eff.smtp_user,
            "from_addr": eff.smtp_from_addr,
            "to_addr": eff.smtp_to_addr,
            "use_tls": eff.smtp_use_tls,
            "privacy_mode": eff.notification_privacy_mode,
            "smtp_key": f"已通过环境变量 {eff.smtp_key_ref} 配置（不回显）",
        }
    raise SettingsValidationError(f"未知 settings section: {section}")


def patch_section(
    db: DBSession,
    *,
    user_id: str,
    section: str,
    patch: dict[str, Any],
    request_id: str | None = None,
) -> dict[str, Any]:
    """PATCH：白名单字段持久化 + 审计（脱敏差异）。返回新视图所需的覆盖。"""
    allowed = _PATCHABLE.get(section)
    if allowed is None:
        raise SettingsValidationError(f"未知 settings section: {section}")
    unknown = set(patch.keys()) - allowed
    if unknown:
        raise SettingsValidationError(f"不可修改的字段: {sorted(unknown)}")
    current = repository.get_value(db, section) or {}
    merged = {**current, **patch}
    repository.set_value(db, section, merged)
    audit_service.append_event(
        db,
        action="settings_patched",
        actor=user_id,
        target_type="settings",
        target_id=section,
        after={"fields": sorted(patch.keys())},
        request_id=request_id,
    )
    db.commit()
    return merged
