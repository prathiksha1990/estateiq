import streamlit as st

from real_estate.ui_chat import process_message
from real_estate.ui_components import execution_details, render_supporting_data
from real_estate.ui_runtime import get_agent_system, reset_conversation

st.title("AI market analyst")
st.caption("Ask EstateIQ to research New Jersey markets using validated SQLite data and the LangGraph agent team.")

with st.container(horizontal=True, horizontal_alignment="right"):
    st.badge("Groq", icon=":material/bolt:", color="green")
    st.badge("Validated answers", icon=":material/verified:", color="blue")
    if st.button("New conversation", icon=":material/add_comment:", key="new_chat"):
        reset_conversation()
        st.rerun()

suggestions = {
    ":material/home:[Westfield value & appreciation]": "What is Westfield's latest home value and five-year appreciation?",
    ":material/compare_arrows:[Westfield vs Summit]": "Compare Westfield and Summit on home values and appreciation.",
    ":material/inventory_2:[Trenton inventory]": "What is the latest for-sale inventory in the Trenton metro?",
}

prompt = st.chat_input(
    "Answer the clarification…" if st.session_state.pending_clarification else "Ask about a New Jersey market…",
    submit_mode="disable",
)
if not st.session_state.messages:
    selected = st.pills("Suggested questions", list(suggestions), label_visibility="collapsed")
    if selected:
        prompt = suggestions[selected]

for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar=":material/smart_toy:" if message["role"] == "assistant" else None):
        if message.get("error"):
            st.error(message["content"], icon=":material/error:")
        elif message.get("clarification"):
            st.info(message["content"], icon=":material/help:")
        else:
            st.markdown(message["content"])

if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant", avatar=":material/smart_toy:"):
        with st.status(":shimmer[EstateIQ is researching]", type="compact") as status:
            outcome = process_message(get_agent_system(), st.session_state, prompt)
            if outcome["status"] == "clarification":
                status.update(label="Clarification needed", state="complete")
                st.info(outcome["message"], icon=":material/help:")
            elif outcome["status"] == "error":
                status.update(label="Research could not complete", state="error")
                st.error(outcome["message"], icon=":material/error:")
            else:
                status.update(label="Research and validation complete", state="complete")
                st.markdown(outcome["message"])
    st.rerun()

if st.session_state.last_agent_state:
    render_supporting_data(st.session_state.last_agent_state)
    execution_details(st.session_state.last_agent_state)
