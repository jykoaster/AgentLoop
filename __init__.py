__all__ = ["workflow", "AgentState"]


def __getattr__(name: str):
    if name == "workflow":
        from .core import app
        return app
    if name == "AgentState":
        from .core import AgentState
        return AgentState
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
