import re
import random

from typing import Optional


def main(text: str) -> Optional[str]:
    match_yes_no = re.fullmatch(r'да +или +нет', text)
    match_randint = re.fullmatch(r'выбери +число(?: +от)? *(\d+)(?: *до| +) *(\d+)', text)
    match_choice = re.fullmatch(r'(выбери +)((?:[^,]+, *)*[^,]+ *(?:или|,) *[^,]+)', text)
    if match_yes_no:
        return "да" if random.random() >= 0.5 else "нет"
    if match_randint:
        return str(random.randint(*map(int, match_randint.groups())))
    if match_choice:
        options = [option.strip() for option in re.split(r', *| *или *', match_choice.group(2)) if option.strip()]
        if len(options) >= 2:
            return random.choice(options)
