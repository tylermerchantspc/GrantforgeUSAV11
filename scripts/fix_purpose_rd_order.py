from pathlib import Path

path = Path('backend/v11_server.py')
text = path.read_text()

start = text.index('def _relevance_compatible(')
end = text.index('\n\ndef _purchaseable_fit', start)
block = text[start:end]

rd_start = block.index('    rd_signals = (')
rd_end_marker = '        return False, "Opportunity requires an R&D/pilot project not identified in the submitted project."\n'
rd_end = block.index(rd_end_marker, rd_start) + len(rd_end_marker)
rd_block = block[rd_start:rd_end]
block_without_rd = block[:rd_start] + block[rd_end:]

insert_marker = '    if client_groups and grant_groups and client_groups.isdisjoint(grant_groups):\n'
insert_at = block_without_rd.index(insert_marker)
new_block = block_without_rd[:insert_at] + rd_block + '\n' + block_without_rd[insert_at:]

text = text[:start] + new_block + text[end:]
path.write_text(text)
print('R&D guard moved ahead of generic purpose rejection')
