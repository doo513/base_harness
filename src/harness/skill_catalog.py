from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from typing import Iterable


class SkillError(ValueError):
    pass


_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    root: Path
    body: str
    compatibility: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    allowed_tools: str | None = None

    @property
    def action(self) -> str | None:
        return self.metadata.get("harness-action")

    @property
    def category(self) -> str:
        return self.metadata.get("category", "general")

    def matches(self, query: str) -> bool:
        tokens = [item for item in query.lower().split() if item]
        if not tokens:
            return True
        haystack = " ".join(
            [self.name, self.description, self.category, self.body[:1200]]
        ).lower()
        return all(token in haystack for token in tokens)


def _strip_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_skill(path: str | Path) -> SkillDefinition:
    skill_path = Path(path)
    text = skill_path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SkillError(f"skill has no YAML frontmatter: {skill_path}")
    try:
        frontmatter, body = text[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise SkillError(f"skill frontmatter is not terminated: {skill_path}") from exc

    values: dict[str, str] = {}
    metadata: dict[str, str] = {}
    section: str | None = None
    for raw_line in frontmatter.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith("  "):
            if section == "metadata" and ":" in raw_line:
                key, value = raw_line.strip().split(":", 1)
                metadata[key.strip()] = _strip_scalar(value)
            continue
        if ":" not in raw_line:
            raise SkillError(f"invalid skill frontmatter line: {raw_line!r}")
        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        section = key if not value else None
        if value:
            values[key] = _strip_scalar(value)

    name = values.get("name", "")
    description = values.get("description", "")
    if not name or not _SKILL_NAME.fullmatch(name):
        raise SkillError(f"invalid skill name: {name!r}")
    if skill_path.parent.name != name:
        raise SkillError(
            f"skill name {name!r} does not match directory {skill_path.parent.name!r}"
        )
    if not description:
        raise SkillError(f"skill description is required: {skill_path}")

    return SkillDefinition(
        name=name,
        description=description,
        compatibility=values.get("compatibility"),
        allowed_tools=values.get("allowed-tools"),
        metadata=metadata,
        body=body.strip(),
        root=skill_path.parent,
    )


class SkillCatalog:
    """Progressively discovers SKILL.md metadata without executing skill content."""

    def __init__(self, skills: Iterable[SkillDefinition] = ()):
        by_name: dict[str, SkillDefinition] = {}
        for skill in skills:
            if skill.name in by_name:
                raise SkillError(f"duplicate skill name: {skill.name}")
            by_name[skill.name] = skill
        self._skills = by_name

    @classmethod
    def from_roots(cls, roots: Iterable[str | Path]) -> "SkillCatalog":
        skills: list[SkillDefinition] = []
        for raw_root in roots:
            root = Path(raw_root).expanduser()
            if not root.exists() or not root.is_dir():
                continue
            for path in sorted(root.glob("*/SKILL.md")):
                skills.append(parse_skill(path))
        return cls(skills)

    @classmethod
    def default(cls, *, workspace: str | Path | None = None) -> "SkillCatalog":
        roots: list[Path] = [Path(__file__).with_name("skills")]
        env_roots = os.environ.get("HARNESS_SKILLS_DIR", "")
        roots.extend(Path(value) for value in env_roots.split(os.pathsep) if value)
        if workspace is not None:
            roots.append(Path(workspace).expanduser() / ".harness" / "skills")
        return cls.from_roots(roots)

    def list(self) -> tuple[SkillDefinition, ...]:
        return tuple(self._skills[name] for name in sorted(self._skills))

    def search(self, query: str = "") -> tuple[SkillDefinition, ...]:
        return tuple(skill for skill in self.list() if skill.matches(query))

    def get(self, name: str) -> SkillDefinition:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise SkillError(f"unknown skill: {name}") from exc
