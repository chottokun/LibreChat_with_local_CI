import os

# Imagine this is the raw output from 'ls -1' in a C locale container
# 'テスト.txt' in UTF-8 is b'\xe3\x83\x86\xe3\x82\xb9\xe3\x83\x88.txt'
# 'ls' might output it as: ''\343\203\206\343\202\271\343\203\210.txt''

raw_output = b"''\\343\\203\\206\\343\\202\\271\\343\\203\\210.txt''\n"
decoded = raw_output.decode('utf-8').splitlines()[0]
print(f"Decoded filename from 'ls': {decoded}")

original = "テスト.txt"
print(f"Original filename: {original}")

if decoded == original:
    print("MATCH")
else:
    print("NO MATCH")

# Now imagine we use python os.listdir which returns bytes or correctly decoded strings if locale is set
# If we use python3 -c "import os; print('\n'.join(os.listdir()))"
# it will respect the environment. If we set PYTHONUTF8=1, it will be UTF-8.
