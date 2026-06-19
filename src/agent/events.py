from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class RunStarted:
    type: str = "RunStarted"
    run_id: str = field(default_factory=_new_id)

    def to_sse(self) -> str:
        return json.dumps({"type": self.type, "run_id": self.run_id})


@dataclass
class TextDelta:
    delta: str
    type: str = "TextDelta"

    def to_sse(self) -> str:
        return json.dumps({"type": self.type, "delta": self.delta})


@dataclass
class ToolCallStart:
    tool_name: str
    tool_call_id: str = field(default_factory=_new_id)
    type: str = "ToolCallStart"

    def to_sse(self) -> str:
        return json.dumps(
            {"type": self.type, "tool_name": self.tool_name, "tool_call_id": self.tool_call_id}
        )


@dataclass
class ToolCallResult:
    tool_call_id: str
    result: str
    type: str = "ToolCallResult"

    def to_sse(self) -> str:
        return json.dumps(
            {"type": self.type, "tool_call_id": self.tool_call_id, "result": self.result}
        )


@dataclass
class UiAction:
    payload: dict
    action: str = "order_card"
    type: str = "CustomEvent"
    name: str = "ui_action"

    def to_sse(self) -> str:
        return json.dumps({
            "type": self.type,
            "name": self.name,
            "value": {"action": self.action, "payload": self.payload},
        })


@dataclass
class RunFinished:
    type: str = "RunFinished"

    def to_sse(self) -> str:
        return json.dumps({"type": self.type})
