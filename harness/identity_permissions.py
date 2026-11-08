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
