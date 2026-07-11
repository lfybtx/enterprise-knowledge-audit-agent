from app.services.chunking import build_chunks, format_location


def test_long_paragraph_is_split_with_same_location():
    text = "客户名单导出必须经过区域经理审批。" * 40
    chunks = build_chunks(
        "document-1",
        [{"text": text, "location": {"kind": "page", "page_number": 2}}],
        max_chars=80,
        overlap_chars=12,
    )

    assert len(chunks) > 1
    assert all(chunk["location"] == {"kind": "page", "page_number": 2} for chunk in chunks)
    assert chunks[0]["id"] == "document-1-chunk-1"


def test_table_row_is_not_split():
    text = "风险等级: 高 | 建议动作: 在工单中保留区域经理审批记录。" * 20
    chunks = build_chunks(
        "document-1",
        [{"text": text, "location": {"kind": "table_row", "table_number": 1, "row_number": 2}}],
        max_chars=80,
    )

    assert len(chunks) == 1
    assert format_location(chunks[0]["location"]) == "表格 1，第 2 行"


def test_location_labels_are_human_readable():
    assert format_location({"kind": "page", "page_number": 3}) == "第 3 页"
    assert format_location({"kind": "sheet_row", "sheet_name": "客户导出", "row_number": 8}) == "工作表：客户导出，第 8 行"
