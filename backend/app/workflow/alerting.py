"""
Strategy pattern: swap alerting / severity tier logic by component type.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AlertContext:
    component_type: str
    component_id: str
    severity_hint: str


class AlertingStrategy(ABC):
    @abstractmethod
    def alert_tier(self, ctx: AlertContext) -> str:
        """Return P0..P3 style tier."""

    @abstractmethod
    def normalized_severity(self, ctx: AlertContext) -> str:
        """Map incoming severity to dashboard ordering (critical, high, medium, low)."""


class RdbmsAlertStrategy(AlertingStrategy):
    def alert_tier(self, ctx: AlertContext) -> str:
        return "P0"

    def normalized_severity(self, ctx: AlertContext) -> str:
        return "critical"


class ApiAlertStrategy(AlertingStrategy):
    def alert_tier(self, ctx: AlertContext) -> str:
        return "P1"

    def normalized_severity(self, ctx: AlertContext) -> str:
        if ctx.severity_hint.lower() in ("critical", "high"):
            return "high"
        return "medium"


class CacheAlertStrategy(AlertingStrategy):
    def alert_tier(self, ctx: AlertContext) -> str:
        return "P2"

    def normalized_severity(self, ctx: AlertContext) -> str:
        return "medium"


class McpHostAlertStrategy(AlertingStrategy):
    def alert_tier(self, ctx: AlertContext) -> str:
        return "P1"

    def normalized_severity(self, ctx: AlertContext) -> str:
        return "high"


class QueueAlertStrategy(AlertingStrategy):
    def alert_tier(self, ctx: AlertContext) -> str:
        return "P1"

    def normalized_severity(self, ctx: AlertContext) -> str:
        return "high"


class NosqlAlertStrategy(AlertingStrategy):
    def alert_tier(self, ctx: AlertContext) -> str:
        return "P1"

    def normalized_severity(self, ctx: AlertContext) -> str:
        return "high"


class DefaultAlertStrategy(AlertingStrategy):
    def alert_tier(self, ctx: AlertContext) -> str:
        return "P3"

    def normalized_severity(self, ctx: AlertContext) -> str:
        return ctx.severity_hint.lower() if ctx.severity_hint else "low"


_STRATEGIES: dict[str, AlertingStrategy] = {
    "RDBMS": RdbmsAlertStrategy(),
    "API": ApiAlertStrategy(),
    "CACHE": CacheAlertStrategy(),
    "MCP_HOST": McpHostAlertStrategy(),
    "QUEUE": QueueAlertStrategy(),
    "NOSQL": NosqlAlertStrategy(),
}


def get_alerting_strategy(component_type: str) -> AlertingStrategy:
    key = component_type.upper().replace(" ", "_")
    return _STRATEGIES.get(key, DefaultAlertStrategy())
