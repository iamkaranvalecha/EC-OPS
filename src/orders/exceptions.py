class OrderNotFound(Exception):
    def __init__(self, order_id: object) -> None:
        short = str(order_id)[:8] + "..."
        super().__init__(f"Order {short} not found")


class OrderNotCancellable(Exception):
    def __init__(self, order_id: object, status: str) -> None:
        short = str(order_id)[:8] + "..."
        super().__init__(f"Order {short} cannot be cancelled (status: {status})")


class OrderStatusTransitionError(Exception):
    def __init__(self, order_id: object, from_status: str, to_status: str) -> None:
        short = str(order_id)[:8] + "..."
        super().__init__(
            f"Order {short} cannot transition from {from_status} to {to_status}"
        )
