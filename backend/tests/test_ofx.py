"""OFX / QFX statement files (OFX 1.x SGML and 2.x XML), and the upload route picking the right reader."""

from datetime import date

import pytest

from clawback.sources.statements import is_ofx, parse_ofx, parse_upload
from clawback.store import store

# OFX 1.x: SGML header, leaf tags never closed, Windows line endings, an entity in a name.
OFX_SGML = (
    "OFXHEADER:100\r\nDATA:OFXSGML\r\nVERSION:102\r\nSECURITY:NONE\r\nENCODING:USASCII\r\nCHARSET:1252\r\n"
    "COMPRESSION:NONE\r\nOLDFILEUID:NONE\r\nNEWFILEUID:NONE\r\n\r\n"
    "<OFX><SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO</STATUS><DTSERVER>20261020120000</SONRS>"
    "</SIGNONMSGSRSV1><BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STMTRS><CURDEF>USD"
    "<BANKACCTFROM><BANKID>123456789<ACCTID>000111222<ACCTTYPE>CHECKING</BANKACCTFROM>\r\n"
    "<BANKTRANLIST><DTSTART>20260901<DTEND>20261020\r\n"
    "<STMTTRN>\r\n<TRNTYPE>DEBIT\r\n<DTPOSTED>20261001120000.000[-5:EST]\r\n<TRNAMT>-17.99\r\n"
    "<FITID>2026100101\r\n<NAME>NETFLIX.COM\r\n<MEMO>866-579-7172 CA\r\n</STMTTRN>\r\n"
    "<STMTTRN>\r\n<TRNTYPE>DEBIT\r\n<DTPOSTED>20261003\r\n<TRNAMT>-42.10\r\n"
    "<FITID>2026100302\r\n<NAME>BARNES &amp; NOBLE #2231\r\n</STMTTRN>\r\n"
    "<STMTTRN>\r\n<TRNTYPE>CREDIT\r\n<DTPOSTED>20261005\r\n<TRNAMT>1500.00\r\n"
    "<FITID>2026100503\r\n<NAME>PAYROLL ACME INC\r\n</STMTTRN>\r\n"
    "<STMTTRN>\r\n<TRNTYPE>DEBIT\r\n<DTPOSTED>20261007\r\n<TRNAMT>-11.99\r\n"
    "<FITID>2026100704\r\n<MEMO>SPOTIFY USA\r\n</STMTTRN>\r\n"
    "</BANKTRANLIST><LEDGERBAL><BALAMT>2000.00<DTASOF>20261020</LEDGERBAL></STMTRS></STMTTRNRS>"
    "</BANKMSGSRSV1></OFX>\r\n"
)

# OFX 2.x: XML, every tag closed; a credit card statement; one leaf on the same line as the next.
OFX_XML = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<?OFX OFXHEADER="200" VERSION="220" SECURITY="NONE" OLDFILEUID="NONE" NEWFILEUID="NONE"?>
<OFX>
  <CREDITCARDMSGSRSV1>
    <CCSTMTTRNRS>
      <TRNUID>1</TRNUID>
      <CCSTMTRS>
        <CURDEF>USD</CURDEF>
        <CCACCTFROM><ACCTID>4111000011112222</ACCTID></CCACCTFROM>
        <BANKTRANLIST>
          <DTSTART>20260901</DTSTART><DTEND>20261020</DTEND>
          <STMTTRN>
            <TRNTYPE>DEBIT</TRNTYPE>
            <DTPOSTED>20261012000000[0:GMT]</DTPOSTED>
            <TRNAMT>-89.99</TRNAMT>
            <FITID>CC-9001</FITID>
            <NAME>BEST BUY 00012345</NAME>
          </STMTTRN>
          <STMTTRN><TRNTYPE>DEBIT</TRNTYPE><DTPOSTED>20261013</DTPOSTED><TRNAMT>-89.99</TRNAMT><FITID>CC-9002</FITID><NAME>BEST BUY 00012345</NAME></STMTTRN>
          <STMTTRN>
            <TRNTYPE>CREDIT</TRNTYPE>
            <DTPOSTED>20261015</DTPOSTED>
            <TRNAMT>25.00</TRNAMT>
            <FITID>CC-9003</FITID>
            <NAME>REFUND AMAZON</NAME>
          </STMTTRN>
        </BANKTRANLIST>
      </CCSTMTRS>
    </CCSTMTTRNRS>
  </CREDITCARDMSGSRSV1>
</OFX>
"""


def test_sgml_ofx():
    txs = parse_ofx(OFX_SGML)
    assert [(t.date, t.description, t.amount) for t in txs] == [
        (date(2026, 10, 1), "NETFLIX.COM", 17.99),  # money out is positive, as in our model
        (date(2026, 10, 3), "BARNES & NOBLE #2231", 42.10),  # &amp; unescaped
        (date(2026, 10, 5), "PAYROLL ACME INC", -1500.00),
        (date(2026, 10, 7), "SPOTIFY USA", 11.99),  # no NAME: MEMO is used
    ]
    assert {t.source for t in txs} == {"statement"}
    assert len({t.id for t in txs}) == 4 and all(t.id.startswith("ofx-") for t in txs)


def test_xml_ofx_credit_card():
    txs = parse_ofx(OFX_XML)
    assert [(t.date, t.description, t.amount) for t in txs] == [
        (date(2026, 10, 12), "BEST BUY 00012345", 89.99),
        (date(2026, 10, 13), "BEST BUY 00012345", 89.99),
        (date(2026, 10, 15), "REFUND AMAZON", -25.00),
    ]


def test_ids_are_stable_and_follow_the_account():
    assert [t.id for t in parse_ofx(OFX_SGML)] == [t.id for t in parse_ofx(OFX_SGML)]
    other_account = OFX_SGML.replace("<ACCTID>000111222", "<ACCTID>999888777")
    assert parse_ofx(OFX_SGML)[0].id != parse_ofx(other_account)[0].id


def test_bad_rows_are_skipped_and_empty_files_rejected():
    broken = OFX_SGML.replace("<DTPOSTED>20261003", "<DTPOSTED>not-a-date").replace("<TRNAMT>-11.99", "<TRNAMT>abc")
    assert [t.description for t in parse_ofx(broken)] == ["NETFLIX.COM", "PAYROLL ACME INC"]
    with pytest.raises(ValueError):
        parse_ofx("OFXHEADER:100\n<OFX><BANKMSGSRSV1></BANKMSGSRSV1></OFX>")
    with pytest.raises(ValueError):
        parse_ofx("Date,Description,Amount\n2026-10-01,GYM,-20.00\n")


def test_decimal_comma_and_missing_end_tags():
    loose = ("OFXHEADER:100\n<OFX><BANKTRANLIST>"
             "<STMTTRN><DTPOSTED>20261001<TRNAMT>-9,99<FITID>a<NAME>HULU"
             "<STMTTRN><DTPOSTED>20261002<TRNAMT>-5.00<FITID>b<NAME>COFFEE"
             "</BANKTRANLIST></OFX>")
    assert [(t.description, t.amount) for t in parse_ofx(loose)] == [("HULU", 9.99), ("COFFEE", 5.00)]


def test_sniffing_and_dispatch():
    assert is_ofx("anything", "Statement.QFX") and is_ofx(OFX_XML) and is_ofx(OFX_SGML, "export.txt")
    assert not is_ofx("Date,Description,Amount\n", "s.csv")
    assert parse_upload(OFX_SGML.encode("cp1252"), "bank.ofx")[0] == "ofx"
    assert parse_upload(OFX_XML.encode(), None)[0] == "ofx"  # by content
    kind, txs = parse_upload("﻿Date,Description,Amount\n2026-10-01,GYM,-20.00\n".encode(), "s.csv")
    assert kind == "csv" and txs[0].amount == 20.0
    # Windows-1252 bytes that aren't valid UTF-8 still decode
    kind, txs = parse_upload(OFX_SGML.replace("BARNES &amp; NOBLE", "CAF\xc9 NOIR").encode("cp1252"), "x.qfx")
    assert any(t.description.startswith("CAF\xc9") for t in txs)


def test_upload_route_reads_ofx_once(client):
    store.reset("demo")
    files = {"file": ("statement.qfx", OFX_SGML.encode(), "application/octet-stream")}
    first = client.post("/api/ingest/statement", files=files)
    assert first.status_code == 200 and first.json()["added_transactions"] == 4 and first.json()["format"] == "ofx"
    again = client.post("/api/ingest/statement", files=files)
    assert again.json()["added_transactions"] == 0  # same FITIDs: nothing added twice
    assert sum(1 for t in store.user("demo").transactions if t.id.startswith("ofx-")) == 4

    bad = client.post("/api/ingest/statement", files={"file": ("x.ofx", b"OFXHEADER:100\n<OFX></OFX>")})
    assert bad.status_code == 400 and "No transactions" in bad.json()["detail"]
    csv = client.post("/api/ingest/statement", files={"file": ("s.csv", b"Date,Description,Amount\n2026-10-01,GYM,-20.00\n")})
    assert csv.status_code == 200 and csv.json()["format"] == "csv"
