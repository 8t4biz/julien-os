import sys

from openai import OpenAI

sys.path.insert(0, "/root")
from julien_os.config import OPENAI_API_KEY

openai_client = OpenAI(api_key=OPENAI_API_KEY)


async def transcrire_audio(chemin_fichier: str) -> str:
    with open(chemin_fichier, "rb") as f:
        transcription = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="fr"
        )
    return transcription.text
