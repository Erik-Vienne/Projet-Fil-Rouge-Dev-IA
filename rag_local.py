"""Recherche semantique locale, sans service d'embeddings Azure."""

import os
from typing import Protocol

import numpy as np

from agent import normaliser


MODELE_DEFAUT = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Tokenizer(Protocol):
    def num_special_tokens_to_add(self, pair: bool = False) -> int: ...

    def encode(
        self, texte: str, *, add_special_tokens: bool, truncation: bool, verbose: bool,
    ) -> list[int]: ...

    def decode(self, tokens: list[int], *, skip_special_tokens: bool) -> str: ...


class Encodeur(Protocol):
    max_seq_length: int
    tokenizer: Tokenizer

    def encode(self, textes: list[str], **options) -> np.ndarray: ...


def charger_modele() -> Encodeur:
    from sentence_transformers import SentenceTransformer

    nom = os.getenv("LOCAL_EMBEDDING_MODEL", MODELE_DEFAUT).strip()
    if not nom:
        raise ValueError("LOCAL_EMBEDDING_MODEL ne peut pas etre vide.")
    try:
        return SentenceTransformer(nom, device="cpu", trust_remote_code=False)
    except (OSError, ValueError) as erreur:
        raise OSError(
            "Chargement du modele d'embeddings local impossible. Au premier lancement, "
            "un acces a Hugging Face est necessaire pour le telecharger. "
            "LOCAL_EMBEDDING_MODEL peut aussi designer un dossier de modele local."
        ) from erreur


def verifier_vecteurs(vecteurs, nombre, dimension=None):
    matrice = np.asarray(vecteurs, dtype=float)
    if (
        matrice.ndim != 2 or matrice.shape[0] != nombre or matrice.shape[1] == 0
        or (dimension is not None and matrice.shape[1] != dimension)
        or not np.isfinite(matrice).all()
    ):
        raise ValueError("Embeddings locaux invalides ou de dimensions incoherentes.")
    normes = np.linalg.norm(matrice, axis=1, keepdims=True)
    if not np.isfinite(normes).all() or (normes == 0).any():
        raise ValueError("Norme d'embedding local invalide.")
    return matrice / normes


class IndexLocal:
    def __init__(self, pages, modele: Encodeur):
        self.modele = modele
        self.extraits = []
        tokenizer = modele.tokenizer
        taille = modele.max_seq_length - tokenizer.num_special_tokens_to_add(pair=False)
        if taille <= 0:
            raise ValueError("Taille de contexte du modele local invalide.")
        chevauchement = min(32, taille // 4)
        for page in pages:
            tokens = tokenizer.encode(
                page["texte"], add_special_tokens=False, truncation=False, verbose=False,
            )
            if not tokens:
                raise ValueError(f"Texte vide : {page['document']}, page {page['page']}.")
            for numero, debut in enumerate(range(0, len(tokens), taille - chevauchement), 1):
                self.extraits.append({
                    **page, "extrait": numero,
                    "texte": tokenizer.decode(tokens[debut:debut + taille], skip_special_tokens=True),
                })
                if debut + taille >= len(tokens):
                    break
        if not self.extraits:
            raise ValueError("Aucun extrait PDF a indexer.")
        self.vecteurs = verifier_vecteurs(
            modele.encode(
                [e["texte"] for e in self.extraits],
                batch_size=16, show_progress_bar=False, convert_to_numpy=True,
            ),
            len(self.extraits),
        )

    def rechercher(self, recherche="", fournisseur="", nombre=5):
        if type(nombre) is not int or not 1 <= nombre <= 20:
            raise ValueError("nombre doit etre un entier entre 1 et 20.")
        nom = normaliser(fournisseur)
        documents = {
            e["document"] for e in self.extraits
            if not nom or nom in normaliser(e["document"] + " " + e["texte"])
        }
        candidats = [i for i, e in enumerate(self.extraits) if e["document"] in documents]
        resultats = [dict(self.extraits[i]) for i in candidats]
        tronque = False
        if recherche.strip() and candidats:
            vecteur = verifier_vecteurs(
                self.modele.encode(
                    [recherche.strip()], show_progress_bar=False, convert_to_numpy=True,
                ),
                1, self.vecteurs.shape[1],
            )[0]
            scores = self.vecteurs[candidats] @ vecteur
            classement = sorted(zip(candidats, scores), key=lambda e: e[1], reverse=True)
            tronque = len(classement) > nombre
            resultats = [
                {**self.extraits[i], "score": float(score)}
                for i, score in classement[:nombre]
            ]
        return {
            "source": "Fiches fournisseurs PDF",
            "recherche": "semantique locale" if recherche.strip() else "consultation",
            "tronque": tronque,
            "nombre_pages": len({(e["document"], e["page"]) for e in resultats}),
            "resultats": resultats,
        }
