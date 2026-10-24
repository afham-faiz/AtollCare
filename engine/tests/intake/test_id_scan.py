import base64
from datetime import date

import pytest

from app.intake import config, ocr_service
from app.intake.ocr_service import IdReading, age_on, parse_identity_doc
from app.intake.video_prep import normalise_image

# A valid 1x1 PNG, so uploads look like real images.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")
TODAY = date(2026, 10, 24)

GOOD = IdReading(document_type="UK driving licence", surname="MC-FUNNY", given_names="DAVID",
                 date_of_birth="1990-01-01", id_number="DAVID901014MF9AA")


def reads(reading: IdReading):
    return lambda image, mime: (reading, "gemini-3.8-flash")


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")


# ---------------------------------------------------------------- reading -> Demographics

def test_a_clean_read_needs_no_review(monkeypatch, with_key):
    monkeypatch.setattr(ocr_service, "_read_with_gemini", reads(GOOD))
    result = parse_identity_doc(PNG, today=TODAY)
    assert result.full_name == "DAVID MC-FUNNY"          # given names first, as the PRD's full_name
    assert result.id_number == "DAVID901014MF9AA"
    assert result.date_of_birth == "1990-01-01" and result.age == 36
    assert result.insurance_status == "UNKNOWN"          # a licence says nothing about insurance
    assert not result.needs_review and result.issues == []


def test_specimen_cards_are_flagged_but_still_read(monkeypatch, with_key):
    monkeypatch.setattr(ocr_service, "_read_with_gemini", reads(GOOD.model_copy(update={"is_specimen": True})))
    result = parse_identity_doc(PNG, today=TODAY)
    assert result.full_name == "DAVID MC-FUNNY" and result.needs_review
    assert any("specimen" in i for i in result.issues)


def test_unreadable_fields_are_null_not_guessed(monkeypatch, with_key):
    covered = IdReading(surname="MC-FUNNY", text_partly_obscured=True, legibility_issues=["ID number under a thumb"])
    monkeypatch.setattr(ocr_service, "_read_with_gemini", reads(covered))
    result = parse_identity_doc(PNG, today=TODAY)
    assert result.full_name == "MC-FUNNY"
    assert result.id_number is None and result.age is None and result.date_of_birth is None
    assert result.needs_review
    assert "ID number under a thumb" in result.issues
    assert "Could not read the ID number." in result.issues


@pytest.mark.parametrize("bad", ["N/A", "??", "x", "!!!!!!", "a" * 60])
def test_an_implausible_id_number_is_dropped(monkeypatch, with_key, bad):
    monkeypatch.setattr(ocr_service, "_read_with_gemini", reads(GOOD.model_copy(update={"id_number": bad})))
    result = parse_identity_doc(PNG, today=TODAY)
    assert result.id_number is None and result.needs_review


@pytest.mark.parametrize("dob", ["01.01.1990", "1990-13-45", "tomorrow", "2999-01-01"])
def test_a_bad_or_future_birth_date_gives_no_age(monkeypatch, with_key, dob):
    monkeypatch.setattr(ocr_service, "_read_with_gemini", reads(GOOD.model_copy(update={"date_of_birth": dob})))
    result = parse_identity_doc(PNG, today=TODAY)
    assert result.age is None and result.date_of_birth is None and result.needs_review


def test_age_changes_on_the_birthday_not_before():
    born = date(1990, 10, 25)
    assert age_on(born, date(2026, 10, 24)) == 35
    assert age_on(born, date(2026, 10, 25)) == 36


# ---------------------------------------------------------------- never raises

def test_a_failing_read_returns_empty_demographics_with_the_reason(monkeypatch, with_key):
    def boom(image, mime):
        raise RuntimeError("503 overloaded")
    monkeypatch.setattr(ocr_service, "_read_with_gemini", boom)
    result = parse_identity_doc(PNG, today=TODAY)
    assert result.full_name is None and result.id_number is None and result.needs_review
    assert "503 overloaded" in result.issues[0]


def test_no_api_key_is_reported_not_raised():
    result = parse_identity_doc(PNG)
    assert result.needs_review and "GEMINI_API_KEY" in result.issues[0]


def test_garbage_bytes_do_not_raise(monkeypatch, with_key):
    result = parse_identity_doc(b"this is not an image")
    assert result.full_name is None and result.needs_review and result.issues[0].startswith("read_failed")


# ---------------------------------------------------------------- image preparation

def test_normal_images_are_sent_untouched():
    assert normalise_image(PNG) == (PNG, "image/png")
    jpeg = b"\xff\xd8\xff\xe0" + bytes(100)
    assert normalise_image(jpeg) == (jpeg, "image/jpeg")


def test_a_non_image_is_rejected():
    with pytest.raises(ValueError):
        normalise_image(b"hello world")


# ---------------------------------------------------------------- endpoint


