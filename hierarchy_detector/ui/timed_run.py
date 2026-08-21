"""Runs a slow, non-Streamlit computation on a background thread while the
main script thread polls it, so a live elapsed-seconds counter can update in
real time without blocking Streamlit's UI streaming.

The worker thread must never call any st.* API — Streamlit's script context
is thread-local, so only the main thread (the one Streamlit is actually
executing the script on) may touch st.* elements."""

from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

import streamlit as st

T = TypeVar("T")

_POLL_INTERVAL_SECONDS = 0.2


def run_with_live_timer(fn: Callable[[], T], label: str) -> T:
    """Runs fn() on a background thread; meanwhile shows `label` (via
    st.spinner) plus a live-ticking elapsed-seconds caption that's cleared as
    soon as fn() returns. Re-raises, on the calling thread, any exception
    fn() raised."""
    outcome: dict = {}
    done = threading.Event()

    def _worker() -> None:
        try:
            outcome["value"] = fn()
        except Exception as exc:  # re-raised on the main thread below
            outcome["error"] = exc
        finally:
            done.set()

    start = time.perf_counter()
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    counter = st.empty()
    with st.spinner(label):
        while not done.wait(timeout=_POLL_INTERVAL_SECONDS):
            counter.caption(f"{time.perf_counter() - start:.1f}s elapsed")
    counter.empty()

    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]
