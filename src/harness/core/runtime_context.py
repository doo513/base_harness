from __future__ import annotations


class RuntimeContextMixin:
    """Model-visible Context Governor projection boundary."""

    def _context(self) -> dict:
        return self.context_projector.project(
            goal=self.goal,
            state=self.state,
            tools=self.actions.tools,
        )
