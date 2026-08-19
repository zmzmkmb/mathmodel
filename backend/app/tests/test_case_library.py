from app.tools.case_library import LocalCaseLibrary


def test_local_case_library_ranks_matching_cards(tmp_path):
    (tmp_path / "traffic.md").write_text(
        "# Traffic flow forecasting\n\nRegression and sensitivity analysis.",
        encoding="utf-8",
    )
    (tmp_path / "unrelated.md").write_text(
        "# Crop disease\n\nImage classification.",
        encoding="utf-8",
    )

    hits = LocalCaseLibrary(str(tmp_path)).search("traffic regression", limit=3)

    assert [hit.case_id for hit in hits] == ["traffic"]
    assert hits[0].score > 0
