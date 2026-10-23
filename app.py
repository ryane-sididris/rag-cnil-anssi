"""streamlit run app.py"""
import time

import streamlit as st

import config
from rag import answer, connect

MODE_LABELS = {
    "Hybride (sens + mots-clés)": "hybrid",
    "Sens (vectorielle)": "vector",
    "Mots-clés (plein texte)": "keyword",
}

st.set_page_config(page_title="RAG CNIL / ANSSI")


@st.cache_resource
def get_conn():
    return connect()


with st.sidebar:
    st.header("Réglages")
    mode = MODE_LABELS[st.radio("Recherche", list(MODE_LABELS))]
    k = st.slider("Nombre d'extraits", 2, 8, config.TOP_K)
    st.caption(f"LLM : {config.LLM_MODEL} · embeddings : {config.EMBED_MODEL}")

st.title("Questions sur les guides CNIL et ANSSI")
st.caption("Réponses générées en local, à partir des documents uniquement.")

with st.form("question"):
    question = st.text_input("Votre question")
    submitted = st.form_submit_button("Demander")

if submitted and question.strip():
    with st.spinner("Recherche et génération..."):
        start = time.time()
        reply, chunks = answer(get_conn(), question, mode, k)
        elapsed = time.time() - start

    st.markdown(reply)
    st.caption(f"{elapsed:.0f} s")

    if chunks:
        st.subheader("Extraits utilisés")
        for i, c in enumerate(chunks, start=1):
            with st.expander(f"[{i}] {c['doc']}, p. {c['page']} · score {c['score']:.3f}"):
                st.write(c["content"])
