import pytest

from app.cli.wordstat import get_top_words


def test_basic_word_count(tmp_path):
    file = tmp_path / "sample.txt"
    file.write_text("apple banana apple orange banana apple")

    result = get_top_words(str(file), 2)

    assert result == [("apple", 3), ("banana", 2)]


def test_case_insensitive_count(tmp_path):
    file = tmp_path / "sample.txt"
    file.write_text("Python python PYTHON Java")

    result = get_top_words(str(file))

    assert result[0] == ("python", 3)


def test_empty_file(tmp_path):
    file = tmp_path / "empty.txt"
    file.write_text("")

    result = get_top_words(str(file))

    assert result == []


def test_missing_file(tmp_path):
    file = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError, match="File not found"):
        get_top_words(str(file))


def test_top_n_limit(tmp_path):
    file = tmp_path / "sample.txt"
    file.write_text("a b c a b c a")

    result = get_top_words(str(file), 2)

    assert len(result) == 2
    assert result == [("a", 3), ("b", 2)]


def test_unicode_words(tmp_path):
    file = tmp_path / "unicode.txt"
    file.write_text("café café naïve résumé", encoding="utf-8")

    result = get_top_words(str(file))

    assert result == [("café", 2), ("naïve", 1), ("résumé", 1)]


def test_very_long_line(tmp_path):
    file = tmp_path / "long.txt"
    file.write_text(("python " * 100000) + "java")

    result = get_top_words(str(file), 2)

    assert result == [("python", 100000), ("java", 1)]


def test_punctuation_and_numbers(tmp_path):
    file = tmp_path / "punctuation.txt"
    file.write_text("hello, world! hello world.")

    result = get_top_words(str(file))

    assert result == [("hello", 2), ("world", 2)]
