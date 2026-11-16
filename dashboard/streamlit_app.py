"""Operations dashboard page. Run from the repository root:

    pip install -r dashboard/requirements.txt
    streamlit run dashboard/streamlit_app.py

It reads the same Supabase project as the API, through the same repository,
using SUPABASE_URL and SUPABASE_SECRET_KEY from `.env`. It only reads.
"""

import sys
from pathlib import Path

import streamlit as st

# Make `app` and `dashboard` importable when Streamlit runs this file as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db import build_repository  # noqa: E402
from dashboard.metrics import compute_metrics, load_rows, recent_cases  # noqa: E402

PERIODS = {"Last 24 hours": 1, "Last 7 days": 7, "Last 30 days": 30, "All time": None}


def tile(column, label: str, percentage: float, note: str = "") -> None:
    """Show one percentage with a short note under it."""
    column.metric(label, f"{percentage} %", note or None, delta_color="off")


st.set_page_config(page_title="Banco Magallanes | Operations", layout="wide")
st.title("Banco Magallanes: agent operations")
st.caption("Resolution, escalation and offers, computed from the bank core's own tables.")

period = st.sidebar.selectbox("Period", list(PERIODS), index=1)
rows = load_rows(build_repository(get_settings()), PERIODS[period])
metrics = compute_metrics(rows)

if metrics["conversations"] == 0:
    st.info("No conversations in this period yet.")

st.subheader("Resolution")
first, second, third, fourth = st.columns(4)
first.metric("Conversations", metrics["conversations"])
tile(
    second,
    "Identity verified",
    metrics["verification_rate"],
    f"{metrics['verified']} conversations",
)
tile(
    third,
    "Resolved by the agent",
    metrics["resolution_rate"],
    f"{metrics['resolved']} conversations",
)
fourth.metric("Verification locked", metrics["locked"])

st.subheader("Escalation")
first, second, third = st.columns(3)
tile(
    first,
    "Escalated to a person",
    metrics["escalation_rate"],
    f"{metrics['escalated']} conversations",
)
second.metric("Cases opened", metrics["cases_total"])
third.metric("Cards blocked", metrics["cards_blocked"])
if metrics["cases_by_type"]:
    st.bar_chart(metrics["cases_by_type"], horizontal=True)

st.subheader("Offers")
first, second, third, fourth = st.columns(4)
first.metric("Offers made", metrics["offers_made"])
tile(second, "Offered to verified customers", metrics["offer_rate"])
tile(third, "Accepted", metrics["acceptance_rate"], f"{metrics['proposals_sent']} proposals sent")
tile(
    fourth, "Signed, of accepted", metrics["signing_rate"], f"{metrics['proposals_signed']} signed"
)
if metrics["offers_by_answer"]:
    st.bar_chart(metrics["offers_by_answer"], horizontal=True)

st.subheader("Latest cases")
st.dataframe(recent_cases(rows), width="stretch", hide_index=True)
