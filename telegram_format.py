"""
Formateur Telegram — convertit la sortie LLM en HTML propre pour Telegram.

Règles :
- parse_mode="HTML" partout (plus prévisible que MarkdownV2)
- **gras** → <b>gras</b>
- *italique* → <i>italique</i>
- `code` → <code>code</code>
- ### Titre / ## Titre / # Titre → <b>Titre</b>
- Tableaux Markdown (lignes avec |) → liste à tirets
- Séquences *** supprimées
- Échappement HTML minimal sur le contenu brut
"""

import re


def _escape_html(text: str) -> str:
    """Échappe les chars HTML dans le contenu (avant d'insérer les balises)."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _convert_table(block: str) -> str:
    """Convertit un bloc de tableau Markdown en liste à tirets."""
    lines = block.strip().split("\n")
    result = []
    for line in lines:
        # Ignore les lignes séparateurs (|---|---|)
        if re.match(r"^\|[\s\-:|]+\|", line):
            continue
        # Extrait les cellules
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        cells = [c for c in cells if c]
        if cells:
            result.append("— " + " · ".join(cells))
    return "\n".join(result)


def format_telegram(text: str) -> str:
    """
    Transforme la sortie LLM (Markdown libre) en HTML valide pour Telegram.
    Retourne le texte formaté + le parse_mode à utiliser.
    """
    if not text:
        return "", "HTML"

    # 1. Détecte et convertit les tableaux Markdown (avant tout le reste)
    #    Un tableau = au moins 2 lignes consécutives commençant par |
    def replace_table(m):
        return _convert_table(m.group(0))

    text = re.sub(
        r"(\|[^\n]+\|\n)+\|[^\n]+\|",
        replace_table,
        text
    )

    # 2. Traite ligne par ligne pour les titres et le contenu
    lines = text.split("\n")
    output_lines = []

    for line in lines:
        # Titres Markdown → <b>
        m = re.match(r"^#{1,3}\s+(.+)$", line)
        if m:
            title = _escape_html(m.group(1).strip())
            output_lines.append(f"<b>{title}</b>")
            continue

        # Lignes de séparation (---, ===, ***) → ligne vide
        if re.match(r"^[-=\*]{3,}\s*$", line):
            output_lines.append("")
            continue

        # Traitement inline du reste de la ligne
        # Échappe d'abord le HTML brut
        line = _escape_html(line)

        # *** (triple astérisque seul ou entourant du texte) → supprimé
        line = re.sub(r"\*{3}(.+?)\*{3}", r"<b>\1</b>", line)
        line = re.sub(r"\*{3}", "", line)

        # **gras**
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)

        # *italique* (en évitant les astérisques déjà traités)
        line = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", line)

        # `code inline`
        line = re.sub(r"`([^`]+)`", r"<code>\1</code>", line)

        output_lines.append(line)

    result = "\n".join(output_lines)

    # 3. Réduit les lignes vides multiples (max 2 consécutives)
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip(), "HTML"


def envoyer_html(text: str, max_len: int = 4096) -> list[str]:
    """
    Formate et découpe en chunks Telegram-compatibles.
    Retourne une liste de strings formatées (HTML).
    """
    formatted, _ = format_telegram(text)
    if len(formatted) <= max_len:
        return [formatted]

    # Découpe proprement sur les sauts de paragraphe
    chunks = []
    current = ""
    for paragraph in formatted.split("\n\n"):
        if len(current) + len(paragraph) + 2 <= max_len:
            current += ("" if not current else "\n\n") + paragraph
        else:
            if current:
                chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks
