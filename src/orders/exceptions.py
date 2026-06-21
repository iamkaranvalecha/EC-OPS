class OrderNotFound(Exception):
    def __init__(self, order_id: object) -> None:
        short = str(order_id)[:8] + "..."
        super().__init__(f"Order {short} not found")


class OrderNotCancellable(Exception):
    def __init__(self, order_id: object, status: str) -> None:
        short = str(order_id)[:8] + "..."
        super().__init__(f"Order {short} cannot be cancelled (status: {status})")
