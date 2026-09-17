from pathlib import Path

from app.salaries import load_salary_csv, salary_coverage


def test_import_keeps_only_attributed_unique_salary(tmp_path: Path):
    source = tmp_path / "salaries.csv"
    source.write_text(
        "player_id,season,base_salary_usd,source_url,checked_at\n"
        "10,2026,1000000,https://example.org/10,2026-09-17\n"
        "11,2026,2000000,,2026-09-17\n"
        "10,2026,3000000,https://example.org/other,2026-09-17\n",
        encoding="utf-8",
    )
    rows, issues = load_salary_csv(source)
    assert [(row.player_id, row.base_salary_usd) for row in rows] == [(10, 1_000_000)]
    assert {issue.code for issue in issues} == {"missing_source", "duplicate_player_season"}


def test_coverage_reports_unpriced_players(tmp_path: Path):
    source = tmp_path / "salaries.csv"
    source.write_text(
        "player_id,season,base_salary_usd,source_url,checked_at\n"
        "10,2026,1000000,https://example.org/10,2026-09-17\n",
        encoding="utf-8",
    )
    rows, _ = load_salary_csv(source)
    coverage = salary_coverage({10, 11}, rows, 2026)
    assert coverage.priced_count == 1
    assert coverage.missing_player_ids == [11]


def test_blank_template_salary_rows_are_skipped(tmp_path: Path):
    source = tmp_path / "template.csv"
    source.write_text(
        "player_id,player_name,season,base_salary_usd,source_url,checked_at\n"
        "10,Named Player,2026,,,\n"
        "11,Priced Player,2026,2000000,https://example.org/11,2026-09-17\n",
        encoding="utf-8",
    )
    rows, issues = load_salary_csv(source)
    assert [row.player_id for row in rows] == [11]
    assert issues == []
