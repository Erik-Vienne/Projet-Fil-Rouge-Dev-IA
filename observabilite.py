"""Journalisation structuree et contexte des requetes de l'assistant."""

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
import sys
import uuid


LOGGER = logging.getLogger("assistant_achats")
_CONTEXTE_REQUETE = contextvars.ContextVar("contexte_requete", default=None)


@dataclass
class ContexteRequete:
    identifiant: str = field(default_factory=lambda: uuid.uuid4().hex)
    outils: list[str] = field(default_factory=list)


class FormateurJSON(logging.Formatter):
    def format(self, record):
        contexte = _CONTEXTE_REQUETE.get()
        evenement = dict(getattr(record, "event_fields", {}))
        donnees = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "niveau": record.levelname,
            "evenement": evenement.pop("evenement"),
        }
        if contexte is not None:
            donnees["request_id"] = contexte.identifiant
        donnees.update(evenement)
        return json.dumps(donnees, ensure_ascii=False, default=str)


def configurer_logs():
    niveau_nom = os.getenv("LOG_LEVEL", "INFO").upper()
    niveau = getattr(logging, niveau_nom, None)
    if not isinstance(niveau, int):
        raise ValueError("LOG_LEVEL doit etre un niveau Python valide.")

    LOGGER.setLevel(niveau)
    LOGGER.propagate = False
    if not any(getattr(handler, "_assistant_achats", False) for handler in LOGGER.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(FormateurJSON())
        handler._assistant_achats = True
        LOGGER.addHandler(handler)


@contextmanager
def contexte_requete():
    contexte = ContexteRequete()
    jeton = _CONTEXTE_REQUETE.set(contexte)
    try:
        yield contexte
    finally:
        _CONTEXTE_REQUETE.reset(jeton)


def enregistrer_outil(nom):
    contexte = _CONTEXTE_REQUETE.get()
    if contexte is not None and nom not in contexte.outils:
        contexte.outils.append(nom)


def journaliser(evenement, niveau=logging.INFO, **champs):
    LOGGER.log(
        niveau,
        evenement,
        extra={"event_fields": {"evenement": evenement, **champs}},
    )
