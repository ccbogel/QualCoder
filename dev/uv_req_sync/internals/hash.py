from hashlib import sha256
from pathlib import Path

# hash from requirements.txt
root=Path(__file__).parent.parent.parent.parent
reqs_txt_file= root/"requirements.txt"
hash_map = root/"dev"/"uv_req_sync"/"hashmap.py"

if not Path.exists(hash_map):

    h = sha256()

    # file
    with open(reqs_txt_file, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    reqs_txt_hash = h.hexdigest()

    with open(reqs_txt_file, "rb") as f:
        lines=f.readlines()
    hash_lines:list[dict]=[]
    for i, line in enumerate(lines):
        line = line.rstrip(b"\r\n")
        line_hash=sha256(line).hexdigest()
        hash_lines.append({i:f"{line_hash}"})
    
    file_str= \
f"""# This file is generated from dev/uv_req_sync/internals/hash.py
# It is used as a "lock" for requirements.txt. Please do not touch
hashmap=\"{hash_map}\"
file_hash=\"{reqs_txt_hash}\"
list_lines_hash={hash_lines}
"""

    with open(hash_map,"w") as w:
        w.write(file_str)