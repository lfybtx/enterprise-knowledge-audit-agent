import pytest

from app.services.parsers import EmptyDocumentError, UnsupportedFileTypeError, parse_document, parse_txt


def test_parse_txt_utf8():
    text = parse_txt("客户名单导出必须经过区域经理审批，导出文件保存不得超过 7 天。".encode("utf-8"))
    assert "区域经理审批" in text


def test_parse_txt_gbk():
    text = parse_txt("客户信息访问必须完成数据保护培训，且不得私自导出。".encode("gbk"))
    assert "数据保护培训" in text


def test_parse_rejects_short_text():
    with pytest.raises(EmptyDocumentError):
        parse_txt("太短".encode("utf-8"))


def test_parse_rejects_unsupported_file_type():
    with pytest.raises(UnsupportedFileTypeError):
        parse_document("policy.pdf", b"fake pdf")
