from __future__ import annotations

from app.services.local_extract import local_extract


class TestLocalExtract:
    def test_simple_task(self):
        result = local_extract("Steuererklärung machen")
        assert result["title"] != ""
        assert "Steuer" in result["title"] or "steuer" in result["title"].lower()
        assert result["priority"] == 3
        assert result["status"] == "offen"

    def test_priority_urgent(self):
        result = local_extract("sofort Müller anrufen")
        assert result["priority"] == 1

    def test_priority_important(self):
        result = local_extract("DSGVO-Auskunft vorbereiten")
        assert result["priority"] == 2

    def test_priority_low(self):
        result = local_extract("bei Gelegenheit Buch sortieren")
        assert result["priority"] == 4

    def test_status_wartend(self):
        result = local_extract("warte auf Antwort von Sabine")
        assert result["status"] == "wartend"
        assert result["waiting_for"] is not None
        assert "Sabine" in result["waiting_for"]

    def test_status_erledigt(self):
        result = local_extract("Steuer erledigt")
        assert result["status"] == "erledigt"

    def test_date_heute(self):
        result = local_extract("Angebot Müller heute fertig")
        assert result["due_at"] is not None
        assert result["due_source_phrase"] == "heute"
        assert "Müller" in result["title"] or "Angebot" in result["title"]

    def test_date_morgen(self):
        result = local_extract("Müller anrufen morgen")
        assert result["due_at"] is not None
        assert "morgen" in result["due_source_phrase"].lower()

    def test_date_naechste_woche(self):
        result = local_extract("Bericht schreiben nächste Woche")
        assert result["due_at"] is not None
        assert "woche" in result["due_source_phrase"].lower()

    def test_tags(self):
        result = local_extract("Bericht erstellen #arbeit #dringend")
        assert "arbeit" in result["tags"]
        assert "dringend" in result["tags"]

    def test_url_extraction(self):
        result = local_extract("Repo anschauen https://github.com/foo/bar")
        assert result["url"] == "https://github.com/foo/bar"
        assert "Repo" in result["title"]

    def test_empty_input(self):
        result = local_extract("")
        assert result["confidence"] == 0.0
        assert "leerer text" in result["ambiguities"]

    def test_confidence_high_simple(self):
        result = local_extract("Steuererklärung machen")
        assert result["confidence"] >= 0.6

    def test_confidence_low_ambiguous(self):
        result = local_extract("Das und jenes machen")
        assert result["confidence"] < 0.7

    def test_no_due_phrase(self):
        result = local_extract("Einfache Aufgabe")
        assert result["due_at"] is None
        assert result["due_source_phrase"] is None

    def test_category_match(self):
        result = local_extract("Angebot Müller erstellen", category_aliases={"Arbeit": ["Müller", "Kunden"]})
        assert result["category"] == "Arbeit"

    def test_subtasks_via_comma(self):
        result = local_extract(
            "Backup machen, Snapshot erstellen und testen"
        )
        assert len(result["subtasks"]) >= 2
        assert any("Backup" in s for s in result["subtasks"])

    def test_low_confidence_triggers_llm_path(self):
        result = local_extract("a b c")
        assert result["confidence"] < 0.6

    def test_status_offen_default(self):
        result = local_extract("irgendwas machen")
        assert result["status"] == "offen"

    def test_title_cleaned(self):
        result = local_extract("Müller anrufen morgen 16 Uhr")
        assert "morgen" not in result["title"].lower()
        assert "16 uhr" not in result["title"].lower()


class TestDateExtract:
    def test_heute(self):
        from app.services.date_extract import find_date_phrase
        phrase, _ = find_date_phrase("Steuer heute")
        assert phrase == "heute"

    def test_morgen(self):
        from app.services.date_extract import find_date_phrase
        phrase, _ = find_date_phrase("Müller morgen anrufen")
        assert phrase == "morgen"

    def test_datum_format(self):
        from app.services.date_extract import find_date_phrase
        phrase, _ = find_date_phrase("Bericht am 15.10.2026")
        assert phrase == "15.10.2026"

    def test_no_date(self):
        from app.services.date_extract import find_date_phrase
        phrase, _ = find_date_phrase("irgendwas ohne datum")
        assert phrase is None


class TestDatePhraseResolution:
    """Regressionstests für die Spannen-basierte Datums-/Zeit-Erkennung."""

    from datetime import datetime

    NOW = datetime(2026, 8, 24, 10, 0)  # Montag, 24.08.2026

    def _resolve(self, text: str):
        r = local_extract(text)
        return r["due_at"], r["due_is_all_day"], r["title"]

    def test_morgen_mit_uhrzeit(self):
        due, all_day, title = self._resolve("Müller anrufen morgen um 8")
        assert due is not None
        assert due.startswith("2026-08-25T08:00")
        assert all_day is False
        assert title == "Müller anrufen"

    def test_morgen_mit_minuten(self):
        due, all_day, _ = self._resolve("Meeting morgen 14:30")
        assert due.startswith("2026-08-25T14:30")
        assert all_day is False

    def test_naechste_woche_samstag(self):
        due, _, _ = self._resolve("Bericht nächste woche samstag fertigstellen")
        # Montag 24.08. → Samstag nächster Woche = 05.09. (nicht 29.08.)
        assert due.startswith("2026-09-05T17:00")

    def test_wochentag_mit_zeit(self):
        due, all_day, title = self._resolve("Zahnarzt am Freitag um 9:30")
        assert due.startswith("2026-08-28T09:30")
        assert all_day is False
        assert title == "Zahnarzt"

    def test_ende_des_monats(self):
        due, _, _ = self._resolve("Steuererklärung bis ende des monats")
        assert due.startswith("2026-08-31T17:00")

    def test_uebermorgen_uhr(self):
        due, _, _ = self._resolve("Teammeeting übermorgen 10 uhr")
        assert due.startswith("2026-08-26T10:00")
        assert due != "2026-08-10"[:10] + "T17:00:00"

    def test_in_n_tagen(self):
        due, _, title = self._resolve("Kaffee in 3 tagen mit Anna trinken")
        assert due.startswith("2026-08-27T17:00")
        assert "in 3 tagen" not in title.lower()

    def test_ende_der_woche(self):
        due, _, _ = self._resolve("Abgabe ende der woche")
        # Freitag derselben Woche = 28.08.
        assert due.startswith("2026-08-28T17:00")

    def test_datum_mit_monatsname(self):
        due, _, _ = self._resolve("Termin am 5. oktober 2026")
        assert due.startswith("2026-10-05T17:00")

    def test_default_time_ohne_zeitangabe(self):
        due, all_day, _ = self._resolve("Anruf morgen")
        assert due.startswith("2026-08-25T17:00")
        assert all_day is True


class TestRecurrenceExtraction:
    """Erkennung von Wiederholungs-Mustern → RRULE."""

    from datetime import datetime

    NOW = datetime(2026, 8, 24, 10, 0)  # Montag

    def _extract(self, text: str):
        r = local_extract(text, now=self.NOW)
        return r["recurrence_rule"], r["title"], r["due_at"]

    def test_jeden_montag(self):
        rule, title, due = self._extract("Statusbericht jeden montag schreiben")
        assert rule == "FREQ=WEEKLY;BYDAY=MO"
        assert "jeden" not in title.lower() and "montag" not in title.lower()
        assert title == "Statusbericht schreiben"
        # nächster Montag nach dem 24.08. = 31.08.
        assert due.startswith("2026-08-31")

    def test_taeglich(self):
        rule, title, _ = self._extract("Müll rausbringen täglich")
        assert rule == "FREQ=DAILY"
        assert title == "Müll rausbringen"

    def test_woechentlich(self):
        rule, _, _ = self._extract("Bericht wöchentlich erstellen")
        assert rule == "FREQ=WEEKLY"

    def test_monatlich_am_ersten(self):
        rule, _, due = self._extract("Miete monatlich am 1. überweisen")
        assert rule == "FREQ=MONTHLY;BYMONTHDAY=1"
        # Tag 1 ist vorbei (24.08.) → nächster Monat
        assert due.startswith("2026-09-01")

    def test_alle_zwei_wochen(self):
        rule, _, due = self._extract("Backup alle 2 wochen prüfen")
        assert rule == "FREQ=WEEKLY;INTERVAL=2"
        assert due.startswith("2026-09-07")  # NOW + 14 Tage

    def test_jaehrlich(self):
        rule, _, _ = self._extract("Versicherung jährlich wechseln")
        assert rule == "FREQ=YEARLY"

    def test_rrule_is_valid(self):
        from dateutil.rrule import rrulestr

        for text in [
            "jeden dienstag standup",
            "täglich meditieren",
            "alle 3 tage gießen",
            "monatlich am 15. bericht",
        ]:
            rule, _, _ = self._extract(text)
            assert rule is not None
            rrulestr(rule)  # darf nicht werfen

    def test_einmalig_kein_recurrence(self):
        """'am Freitag' ohne 'jeden' erzeugt keine Wiederholung."""
        for text in ["Meeting am freitag", "Wohnung putzen am samstag", "Bericht morgen"]:
            rule, _, _ = self._extract(text)
            assert rule is None, f'{text!r} sollte keine Wiederholung haben'
