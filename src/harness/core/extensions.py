from dataclasses import dataclass, field

@dataclass
class SubagentResult:
    status: str
    summary: str
    artifacts: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    cost: dict[str,float] = field(default_factory=dict)

@dataclass
class OptionalGateway:
    retriever: object | None = None
    skill_loader: object | None = None
    subagent_gateway: object | None = None
