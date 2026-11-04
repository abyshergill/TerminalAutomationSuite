import re

def clean_terminal_output(raw_text: str) -> tuple[str, bool]:
    if not raw_text:
        return "", False
    should_clear = bool(re.search(r'\x1b\[[0-9;]*[23]J', raw_text))
    text = re.sub(r'\x1b\].*?(?:\x07|\x1b\\|\n)', '', raw_text)
    text = re.sub(r'\x1b\[[0-9;?<=>]*[a-zA-Z]', '', text)
    text = re.sub(r'\x1b[()#%*+-][0-9A-Za-z]', '', text)
    text = re.sub(r'\x1b[@-Z\\-_]', '', text)
    text = text.replace('\x07', '').replace('\a', '')
    text = text.replace('\r\n', '\n')
    return text, should_clear
