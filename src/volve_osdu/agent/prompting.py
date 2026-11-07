"""Versioned prompts from agent/prompts/*.md: front matter `version`, then System and User parts."""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

PROMPTS = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class Prompt:
    version: str
    system: str
    user: str

    def messages(self, **values: str) -> list[dict[str, str]]:
        user = self.user
        for key, value in values.items():
            user = user.replace("{{" + key + "}}", value)
        if "{{" in user:
            raise ValueError(f"{self.version}: unfilled placeholder in {user[:200]!r}")
        return [{"role": "system", "content": self.system}, {"role": "user", "content": user}]


@cache
def load_prompt(name: str) -> Prompt:
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    front = re.match(r"^---\nversion: (\S+)\n---\n", text)
    if not front:
        raise ValueError(f"{name}.md: missing version front matter")
    body = text[front.end() :]
    system, user = re.split(r"^## User\n", body, maxsplit=1, flags=re.MULTILINE)
    return Prompt(
        version=front.group(1),
        system=system.removeprefix("## System\n").strip(),
        user=user.strip(),
    )
