from app.core.profile import (
    mask_aadhaar,
    validate_aadhaar,
    validate_mobile,
    validate_pan,
    verhoeff_generate,
    verhoeff_validate,
)


def test_verhoeff_roundtrip():
    base = "23456789012"
    full = base + verhoeff_generate(base)
    assert verhoeff_validate(full)
    assert validate_aadhaar(full)


def test_aadhaar_rejects_bad_first_digit_and_length():
    assert not validate_aadhaar("123456789012")  # starts with 1
    assert not validate_aadhaar("2345")  # too short


def test_aadhaar_rejects_bad_checksum():
    base = "23456789012"
    check = verhoeff_generate(base)
    wrong = str((int(check) + 1) % 10)
    assert not validate_aadhaar(base + wrong)


def test_pan():
    assert validate_pan("ABCDE1234F")
    assert not validate_pan("ABC1234567")


def test_mobile():
    assert validate_mobile("9876543210")
    assert not validate_mobile("1234567890")  # starts with 1
    assert not validate_mobile("98765")


def test_mask_aadhaar():
    base = "23456789012"
    full = base + verhoeff_generate(base)
    masked = mask_aadhaar(full)
    assert masked.startswith("XXXX XXXX ")
    assert masked.endswith(full[-4:])
    assert full[:8] not in masked
