import argparse
import re
import sys
from collections import Counter
from pathlib import Path


def get_top_words(file_path, top_n: int = 10):

    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    with Path(file_path).open(encoding="utf-8") as f:
        text = f.read().lower()
        words = re.findall(r"\b\w+\b", text)
    word_counts = Counter(words)
    return word_counts.most_common(top_n)


def main():
    parser = argparse.ArgumentParser(description="Get top N most frequent words in a text file.")
    parser.add_argument("file", help="Path to the text file")
    parser.add_argument("-n", "--top", type=int, default=10, help="Number of top words to display")

    args = parser.parse_args()

    try:
        top_words = get_top_words(args.file, args.top)
        for word, count in top_words:
            sys.stdout.write(f"{word}: {count}\n")
    except FileNotFoundError as e:
        sys.stderr.write(f"Error: {e}\n")


if __name__ == "__main__":
    main()
