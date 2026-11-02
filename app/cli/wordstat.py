import argparse
import re
from collections import Counter
from pathlib import Path


def get_top_words(file_path, top_n: int = 10):

    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read().lower()
        words = re.findall(r'\b\w+\b', text)
    word_counts = Counter(words)
    return word_counts.most_common(top_n)

def main():
    parser = argparse.ArgumentParser(description='Get top N most frequent words in a text file.')
    parser.add_argument('file', help='Path to the text file')
    parser.add_argument('-n', '--top', type=int, default=10, help='Number of top words to display')

    args = parser.parse_args()

    try:
        top_words = get_top_words(args.file, args.top)
        for word, count in top_words:
            print(f'{word}: {count}')
    except FileNotFoundError as e:
        print(e)

if __name__ == '__main__':
    main()
