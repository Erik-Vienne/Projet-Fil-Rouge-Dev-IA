"""Interface web Streamlit pour l'agent Achats."""

import json

import streamlit as st
from openai import APIError
from pypdf.errors import PdfReadError

from agent import creer_agent


def extraire_appels_outils(messages):
    appels = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for appel in message.get("tool_calls", []):
            fonction = appel.get("function", {})
            arguments_bruts = fonction.get("arguments", "{}")
            try:
                arguments = json.loads(arguments_bruts)
            except json.JSONDecodeError:
                arguments = {"arguments": arguments_bruts}
            appels.append({
                "nom": fonction.get("name", "outil inconnu"),
                "arguments": arguments,
            })
    return appels


def afficher_outils(appels):
    if not appels:
        return
    with st.expander("Outils appelés", expanded=False):
        for appel in appels:
            st.markdown(f"**{appel['nom']}**")
            st.json(appel["arguments"])


def afficher_origine_reponse(reponse_en_cache):
    if reponse_en_cache:
        st.caption("Réponse reprise de l’historique, sans nouvel appel au modèle.")


def afficher_consommation(consommation):
    if consommation is None:
        st.caption("Consommation de tokens indisponible.")
        return

    entree = consommation["tokens_entree"]
    sortie = consommation["tokens_sortie"]
    total = consommation["tokens_total"]

    def formater_nombre(nombre):
        return f"{nombre:,}".replace(",", " ")

    st.caption(
        f"Tokens : {formater_nombre(total)} au total "
        f"({formater_nombre(entree)} en entrée, {formater_nombre(sortie)} en sortie)"
    )


def initialiser_agent():
    if "agent" not in st.session_state:
        with st.spinner("Chargement de l’assistant et des fiches fournisseurs…"):
            st.session_state.agent = creer_agent()
    if "conversation" not in st.session_state:
        st.session_state.conversation = []


def main():
    st.set_page_config(page_title="Assistant Achats", page_icon="🛍️")
    st.title("Assistant Achats")
    st.caption("Posez vos questions sur le catalogue et les fournisseurs.")

    with st.sidebar:
        st.subheader("Conversation")
        if st.button("Nouvelle conversation", use_container_width=True):
            if "agent" in st.session_state:
                st.session_state.agent.nouvelle_conversation()
            st.session_state.conversation = []
            st.rerun()

    try:
        initialiser_agent()
    except (APIError, OSError, ValueError, PdfReadError) as erreur:
        st.error(f"Impossible de démarrer l’assistant : {erreur}")
        st.stop()

    for message in st.session_state.conversation:
        with st.chat_message(message["role"]):
            st.markdown(message["contenu"])
            if message["role"] == "assistant":
                afficher_outils(message.get("outils", []))
                afficher_origine_reponse(message.get("reponse_en_cache", False))
                afficher_consommation(message.get("consommation"))

    question = st.chat_input("Écrivez votre question…")
    if not question or not question.strip():
        return

    question = question.strip()
    st.session_state.conversation.append({
        "role": "user",
        "contenu": question,
    })
    with st.chat_message("user"):
        st.markdown(question)

    agent = st.session_state.agent
    debut_historique = len(agent.messages)
    try:
        with st.chat_message("assistant"):
            with st.spinner("Recherche en cours…"):
                reponse = agent.repondre(question)
            en_cache = agent.derniere_reponse_en_cache
            appels = [] if en_cache else extraire_appels_outils(
                agent.messages[debut_historique:]
            )
            st.markdown(reponse)
            afficher_outils(appels)
            afficher_origine_reponse(en_cache)
            consommation = agent.derniere_consommation
            afficher_consommation(consommation)
        st.session_state.conversation.append({
            "role": "assistant",
            "contenu": reponse,
            "outils": appels,
            "consommation": consommation,
            "reponse_en_cache": en_cache,
        })
    except (APIError, OSError, ValueError, PdfReadError) as erreur:
        st.error(f"La réponse n’a pas pu être générée : {erreur}")


if __name__ == "__main__":
    main()
