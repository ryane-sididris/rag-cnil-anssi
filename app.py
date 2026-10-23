"""streamlit run app.py"""
import time

import streamlit as st

import config
from rag import answer, cited_numbers, connect

st.set_page_config(page_title="RAG CNIL / ANSSI")


@st.cache_resource
def get_conn():
    return connect()


st.title("Questions sur les guides CNIL et ANSSI")
st.caption(f"Réponses générées en local ({config.LLM_MODEL}), à partir des documents uniquement.")

with st.form("question"):
    question = st.text_input("Votre question")
    submitted = st.form_submit_button("Demander")

if submitted and question.strip():
    with st.spinner("Recherche et génération..."):
        start = time.time()
        reply, chunks = answer(get_conn(), question)
        elapsed = time.time() - start

    st.markdown(reply)
    st.caption(f"{elapsed:.0f} s")

    numbers = cited_numbers(reply, chunks)
    if numbers:
        st.subheader("Sources")
        for n in numbers:
            c = chunks[n - 1]
            with st.expander(f"[{n}] {c['doc']}, p. {c['page']}"):
                st.write(c["content"])
