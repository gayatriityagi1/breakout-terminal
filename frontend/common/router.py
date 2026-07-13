# -*- coding: utf-8 -*-
"""
router.py — tiny page registry so any view can navigate to any other
(e.g. click a ticker anywhere -> stock page) without import cycles.

terminal.py registers the st.Page objects each run; views call goto().
Navigation params ride along in the URL query string.
"""
import streamlit as st

_pages = {}


def register(name, page):
    _pages[name] = page


def page(name):
    return _pages.get(name)


def goto(name, **params):
    for k, v in params.items():
        st.query_params[k] = str(v)
    target = _pages.get(name)
    if target is not None:
        st.switch_page(target)


def goto_stock(symbol):
    goto("stock", symbol=symbol)


def goto_layer(layer_key):
    goto(f"layer_{layer_key}")
