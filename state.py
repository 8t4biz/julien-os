from typing import Literal, TypedDict

AgentType = Literal[
    "CR", "EMAIL", "SHEPHERD", "MEMOIRE", "PREP", "DIRECT",
    "AIRBNB_SCAN", "PROTON_MAILS",
    "NOTION_NOTE", "NOTION_SEARCH",
]


class AgentState(TypedDict, total=False):
    message: str
    projet: str
    agent: AgentType | None
    contexte: str | None
    resultat: str | None
    alerte: bool | None
    _alertes: list[str]
