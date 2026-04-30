from typing import TypedDict, Optional, Literal, List

AgentType = Literal[
    "CR", "EMAIL", "SHEPHERD", "MEMOIRE", "PREP", "DIRECT",
    "AIRBNB_SCAN", "PROTON_MAILS",
    "NOTION_NOTE", "NOTION_SEARCH",
]


class AgentState(TypedDict, total=False):
    message: str
    projet: str
    agent: Optional[AgentType]
    contexte: Optional[str]
    resultat: Optional[str]
    alerte: Optional[bool]
    _alertes: List[str]
