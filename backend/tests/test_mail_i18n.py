"""Tests für die E-Mail-Lokalisierung (de/en)."""
from __future__ import annotations

from app.services.email import render_summary_html, render_summary_text
from app.services.i18n import normalize_locale, t

USER = {"username": "bernd", "display_name": "Bernd"}
SECTIONS = {
    "ueberfaellig": [{"title": "Task A", "priority": 1, "due_at": "01.08. 10:00", "waiting_for": None}],
    "heute": [{"title": "Task B", "priority": 3, "due_at": None, "waiting_for": "Sabine"}],
}


class TestI18nHelper:
    def test_normalize_locale(self):
        assert normalize_locale("de-DE") == "de"
        assert normalize_locale("de") == "de"
        assert normalize_locale("en-US") == "en"
        assert normalize_locale(None) == "en"
        assert normalize_locale("fr-FR") == "en"

    def test_t_german_and_english(self):
        assert t("de-DE", "summary.intro") == "Hier deine Übersicht für heute:"
        assert t("en-US", "summary.intro") == "Here is your overview for today:"

    def test_t_interpolation(self):
        assert t("de", "waiting_for", who="Sabine") == "wartet auf Sabine"
        assert t("en", "waiting_for", who="Sabine") == "waiting for Sabine"


class TestSummaryRendering:
    def test_text_german(self):
        text = render_summary_text(USER, SECTIONS, locale="de-DE")
        assert "Hallo Bernd," in text
        assert "ÜBERFÄLLIG" in text
        assert "HEUTE FÄLLIG" in text
        assert "wartet auf Sabine" in text

    def test_text_english(self):
        text = render_summary_text(USER, SECTIONS, locale="en-US")
        assert "Hello Bernd," in text
        assert "OVERDUE" in text
        assert "DUE TODAY" in text
        assert "waiting for Sabine" in text

    def test_html_german_vs_english(self):
        html_de = render_summary_html(USER, SECTIONS, locale="de-DE")
        html_en = render_summary_html(USER, SECTIONS, locale="en-US")
        assert "Überfällig" in html_de and "Überfällig" not in html_en
        assert "Overdue" in html_en

    def test_default_is_english_for_unknown_locale(self):
        text = render_summary_text(USER, SECTIONS, locale="zz-ZZ")
        assert "Hello Bernd," in text
