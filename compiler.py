#!/usr/bin/env python3
import sys
import os
import re
import subprocess
import shutil
#stop looking for files somwhere ekse. it is here in the same dirc
def strip_comments_preserve_offsets(content):
    def replacer(match):
        return ' ' * len(match.group(0))
    clean = re.sub(r'/\*.*?\*/', replacer, content, flags=re.DOTALL)
    clean = re.sub(r'//.*', replacer, clean)
    return clean

def split_poly_file(content):
    shadow = strip_comments_preserve_offsets(content)
    go_match = re.search(r'@go', shadow)
    c_match  = re.search(r'@c', shadow)

    if not go_match or not c_match:
        return "", ""

    go_idx = go_match.start()
    c_idx  = c_match.start()

    if go_idx < c_idx:
        go_part = content[go_idx + 3 : c_idx].strip()
        c_part  = content[c_idx + 2 :].strip()
    else:
        c_part  = content[c_idx + 2 : go_idx].strip()
        go_part = content[go_idx + 3 :].strip()

    return go_part, c_part

if len(sys.argv) < 2:
    print("usage: pmc <file1.poly> ...")
    sys.exit(1)

GO_PKG_DIR = "tmp_go_pkg"
if os.path.exists(GO_PKG_DIR):
    shutil.rmtree(GO_PKG_DIR)
os.makedirs(GO_PKG_DIR)

# req for tinygo module resolution
with open("go.mod", "w") as f:
    f.write("module meta_project\n\ngo 1.22\n")

c_ir_files = []
print(f"cc: pass 1 (partition {len(sys.argv)-1} units)")
#why is thi breaking
for i, poly_file in enumerate(sys.argv[1:]):
    try:
        with open(poly_file, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"pmc: error: {poly_file}: No such file or directory")
        sys.exit(1)

    go_part, c_part = split_poly_file(content)
    
    if not go_part and not c_part:
        continue

    with open(os.path.join(GO_PKG_DIR, f"module_{i}.go"), "w") as f:
        f.write(go_part)

    c_src = f"tmp_c_{i}.c"
    c_ir = f"tmp_c_{i}.ll"
    with open(c_src, "w") as f:
        f.write(c_part)
    
    if os.system(f"clang -S -emit-llvm -g {c_src} -o {c_ir}") != 0:
        print(f"clang: error on {poly_file}")
        sys.exit(1)
        
    c_ir_files.append(c_ir)

print("tinygo: emit-llvm")
if os.system(f"tinygo build -o tmp_go_combined.ll -no-debug=true -scheduler=none -gc=leaking ./{GO_PKG_DIR}") != 0:
    print("tinygo: error lowering modules")
    if os.path.exists("go.mod"): os.remove("go.mod")
    sys.exit(1)

print("llvm-link: merging IR")
c_ir_list = " ".join(c_ir_files)
# Output to a RAW file first
if os.system(f"llvm-link {c_ir_list} tmp_go_combined.ll -o unified_raw.ll -S") != 0:
    print("llvm-link: fatal error")
    sys.exit(1)

print("opt: cross-language LTO (-O3)")
# Optimize the fused IR to inline C into Go
if os.system("opt -S -O3 unified_raw.ll -o unified.ll") != 0:
    print("opt: warning: LTO failed, using raw IR")
    os.rename("unified_raw.ll", "unified.ll")

print("z3_verify: executing...")
subprocess.run(["python3", "verify.py", "unified.ll", sys.argv[1]])

extracted_bound = "0"
with open("unified.ll", "r") as f:
    ir_data = f.read()
    lengths = re.findall(r'\[(\d+)\s*x\s*i8\]', ir_data)
    if lengths:
        max_bytes = max(int(l) for l in lengths)
        extracted_bound = str(max_bytes // 4)
        print(f"ir_scan: dyn_bound={extracted_bound}")

print("opt: bounds_chk pass")
subprocess.run(["python3", "instrument.py", extracted_bound])

print("llc: x86_64 target emit (-O3)")
# Generate highly optimized object code
os.system("llc -O3 --relocation-model=pic -filetype=obj unified_hardened.ll -o final.o")
os.system("clang -O3 final.o -no-pie -o pmc_binary")

print("build complete: pmc_binary generated")

# Cleanup
if os.path.exists("go.mod"): os.remove("go.mod")
if os.path.exists("go.sum"): os.remove("go.sum")
if os.path.exists("unified_raw.ll"): os.remove("unified_raw.ll")
if os.path.exists(GO_PKG_DIR): shutil.rmtree(GO_PKG_DIR)
for f in c_ir_files: 
    if os.path.exists(f): os.remove(f)
for i in range(len(sys.argv)-1): 
    if os.path.exists(f"tmp_c_{i}.c"): os.remove(f"tmp_c_{i}.c")
