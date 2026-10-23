"""Seul endroit qui appelle le LLM : pour changer de modèle ou de fournisseur, c'est ici."""
import ollama

import config


def chat(messages):
    response = ollama.chat(
        model=config.LLM_MODEL,
        messages=messages,
        options={"temperature": 0.1, "num_ctx": config.LLM_CONTEXT},
    )
    return response["message"]["content"]
