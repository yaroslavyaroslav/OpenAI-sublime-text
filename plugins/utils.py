import re


def extract_code_blocks(md_text: str):
    """
    Return a list of the contents of each ```…``` code block in the given markdown. The code blocks must extend over multiple lines to be selected
    """
    # compile once
    pattern = re.compile(r"```(?:[^\n`]*)\n([\s\S]*?)```")

    # Remove all inline blocks that the model may generate (i.e. code blocks that are inline with the text or that are single line)
    filtered = re.sub(r"```([^\n]*?)```", "", md_text)

    # Get all the code blocks from the AI completion
    blocks = pattern.findall(filtered)
    # Join all code blocks in a string
    completion_code = "\n\n".join(blocks)
    return completion_code
