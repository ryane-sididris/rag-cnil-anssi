"""streamlit run app.py"""
import time

import streamlit as st

import config
from rag import answer
from search import MODES

st.set_page_config(page_title="Assistant CNIL / ANSSI")

st.title("Questions sur les guides CNIL et ANSSI")
st.caption(f"Réponses générées en local ({config.LLM_MODEL}), uniquement à partir des documents.")

with st.sidebar:
    mode = st.radio("Recherche", MODES, format_func={"hybrid": "hybride", "vector": "vectorielle",
                                                     "keyword": "mots-clés"}.get)
    k = st.slider("Nombre d'extraits (k)", 1, 10, config.TOP_K)

with st.form("question"):
    question = st.text_input("Votre question")
    submitted = st.form_submit_button("Demander")

if submitted and question.strip():
    with st.spinner("Recherche et génération..."):
        start = time.time()
        r = answer(question, k, mode)
        elapsed = time.time() - start

    st.markdown(r["reponse"])
    st.caption(f"{elapsed:.0f} s")
    if r["citations_invalides"]:
        st.warning(f"Identifiants cités mais absents des extraits : {', '.join(r['citations_invalides'])}")

    st.subheader("Extraits récupérés")
    for c in r["chunks"]:
        cite = "cité" if c["chunk_id"] in r["sources"] else "non cité"
        with st.expander(f"[{c['chunk_id']}] {c['title']} – score {c['score']:.4f} – {cite}",
                         expanded=c["chunk_id"] in r["sources"]):
            st.caption(c["source"])
            st.text(c["text"])
