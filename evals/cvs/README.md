# CV extraction evaluation

- `input/`: the 20 synthetic CVs from the Day 5 sample files. All details are invented.
- `gold/`: the correct answers for `cv_01` to `cv_10`, written by a person, not a model.

## How to fill in a gold file

Open `input/cv_NN.txt` next to `gold/cv_NN.json` and type what the CV says.

- Copy text exactly as written: same spelling, same capitals, same punctuation.
- `phone`: as written, for example `"+00 555 588 8287"`.
- `years_experience`: the number in the summary, as a number: `"1 years"` becomes `1`.
- `skills`: one string per skill, as written, in the CV's order: `["SQL", "AWS basics"]`.
- `jobs`: in the CV's order. `"Backend Developer, Stonebridge Software, 2024 to 2025"` becomes
  title `"Backend Developer"`, company `"Stonebridge Software"`, `2024`, `2025`.
- `education`: `"B.Sc Mathematics, graduated 2022"` becomes degree `"B.Sc Mathematics"`, `2022`.
- Years are numbers, not strings: `2024`, not `"2024"`.
- If the CV does not state a value, use `null`. Never leave `""` or an empty list: the scorer
  refuses a gold file that still looks unfilled.

## How answers are scored

Each CV has 8 fields; each is right or wrong.

| Field | Counts as right when |
|---|---|
| name, email, location | equal after trimming spaces and ignoring capitals |
| phone | the same digits |
| years_experience | the same number |
| skills | the same set of skills, ignoring order and capitals |
| jobs | every job matches in order: title, company, start and end year |
| education | every entry matches in order: degree and graduation year |
