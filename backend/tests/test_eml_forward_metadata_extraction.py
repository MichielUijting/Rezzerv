from app.receipt_ingestion.service_parts.text_extraction import _strip_embedded_email_metadata_blocks


def test_forwarded_email_metadata_block_is_removed_without_receipt_words():
    text = """Sender: Person <sender@example.test>
Sent: 1 June 2026 10:18
Recipient: User <user@example.test>
Subject: Forwarded document

22 March 2026
20 March 2026
"""

    cleaned = _strip_embedded_email_metadata_blocks(text)

    assert 'sender@example.test' not in cleaned
    assert '1 June 2026' not in cleaned
    assert '22 March 2026' in cleaned
    assert '20 March 2026' in cleaned


def test_split_field_value_layout_is_removed_structurally():
    text = """Sender:
sender@example.test
Sent:
1 June 2026 10:18
Recipient:
user@example.test
Subject:
Forwarded document

10 May 2026
8 May 2026
"""

    cleaned = _strip_embedded_email_metadata_blocks(text)

    assert 'sender@example.test' not in cleaned
    assert '1 June 2026' not in cleaned
    assert '10 May 2026' in cleaned
    assert '8 May 2026' in cleaned


def test_receipt_like_field_rows_without_email_signal_are_preserved():
    text = """Field A: value
Field B: value
Field C: value

26 April 2026
"""

    cleaned = _strip_embedded_email_metadata_blocks(text)

    assert 'Field A: value' in cleaned
    assert 'Field B: value' in cleaned
    assert 'Field C: value' in cleaned
    assert '26 April 2026' in cleaned
