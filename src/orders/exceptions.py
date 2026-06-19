class OrderNotFound(Exception):
    def __init__(self, order_id: object) -> None:
        super().__init__(f"Order {order_id} not found")


class OrderNotCancellable(Exception):
    def __init__(self, order_id: object, status: str) -> None:
        super().__init__(f"Order {order_id} cannot be cancelled (status: {status})")
