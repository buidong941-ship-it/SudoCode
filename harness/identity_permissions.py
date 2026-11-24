"""Spoken contact data never grants access to a different customer's profile."""
import re


def canonical_phone(value):
    digits = re.sub(r'\D', '', str(value or ''))
    return '0' + digits[2:] if digits.startswith('84') and len(digits) == 11 else digits


def may_bind_spoken_phone(session, phone):
    trusted = getattr(session, 'phone', None)
    if not trusted and getattr(session, 'channel_identity', None):
        # The profile already resolved by the transport channel, never by this sentence.
        trusted = (session.customer or {}).get('phone')
    return bool(canonical_phone(trusted)) and canonical_phone(phone) == canonical_phone(trusted)


def may_forget(session):
    return (bool((session.customer or {}).get('customer_id')) and not session.proxy_caller
            and bool(getattr(session, 'phone', None) or getattr(session, 'channel_identity', None)))


def link_new_spoken_phone(session, value):
    """Chính sách demo được duyệt: CRM chưa có số thì nối vào hồ sơ hiện tại, chặn xung đột."""
    phone = canonical_phone(value)
    if session.proxy_caller or getattr(session, "candidates", None) or not re.fullmatch(r"0[0-9]{9}", phone):
        return {"linked": False, "reason": "proxy_ambiguous_or_invalid"}
    current = session.customer or {}
    if current.get("phone") and canonical_phone(current["phone"]) != phone:
        return {"linked": False, "reason": "profile_phone_conflict"}
    try:
        crm = session.tools.call("crm.get_customer", phone=phone)
        if not isinstance(crm, dict) or crm.get("found") is not False or crm.get("error") or crm.get("ambiguous"):
            return {"linked": False, "reason": "crm_existing_or_unknown"}
        ids = session.mem.lookup("phone", phone)
        cid = current.get("customer_id")
        if any(other != cid for other in ids):
            return {"linked": False, "reason": "memory_phone_conflict"}
        # shortcut: SĐT tự khai được nối khi CRM trống trong demo cố định; cần xác minh sở hữu trước khi dùng thực tế.
        if cid:
            session.mem.upsert_customer(cid, identities_=[("phone", phone)])
            session.customer["phone"] = phone
        else:
            keep = dict(session.known)
            session._bind(f"N-{phone}", None, None, phone, None)
            session.known.update(keep)
        return {"linked": True, "reason": "demo_crm_absent", "phone": phone}
    except Exception:
        return {"linked": False, "reason": "lookup_or_bind_error"}
