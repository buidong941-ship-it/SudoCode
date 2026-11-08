"""Ảnh trạng thái đọc tại đầu lượt cho bộ chọn hành động và điều kiện thực thi."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlannerState:
    stage: str
    focus: str | None
    cart: tuple[str, ...]
    order_ids: tuple[str, ...]
    discussed: tuple[str, ...]
    pending_buy: bool = False
    known: dict = field(default_factory=dict)
    summary: str = ''

    @property
    def has_order(self):
        return bool(self.order_ids)


def snapshot(session):
    previous = (session.brief or {}).get("orders") or []
    order_ids = tuple(dict.fromkeys(
        [o["order_id"] for o in previous + session.orders_created if o.get("order_id")]
    ))
    stage = "after_sale" if order_ids else "cart" if session.cart else "considering" if session.focus else "discovering"
    known = getattr(session, 'known', {})
    return PlannerState(stage, session.focus, tuple(session.cart), order_ids, tuple(session.discussed),
                        bool(getattr(session, 'buy_intent', False)),
                        {k: v for k, v in known.items() if k in ('product_chosen', 'variant_sku', 'size', 'color', 'address', 'payment', 'budget_vnd', 'room_area_m2', 'has_children', 'blocker')},
                        (((session.brief or {}).get('last_session') or {}).get('summary') or '')[:1200])
