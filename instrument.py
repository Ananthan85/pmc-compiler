#!/usr/bin/env python3
import sys
import re

   # try mtatch the GEP lines for i32 arr specifically.
 # grab the result reg,index type,and value for the icmp later. asap.
GEP_RE = re.compile(r'(\%\w+)\s*=\s*getelementptr inbounds i32, ptr\s*(\%\w+),\s*(i32|i64)\s*(\%\w+|\d+)')

def inject_checks(ll_data, b):
    lines = ll_data.split('\n')
    out = []
    
    needs_trap_decl = False
    count = 0

    for line in lines:
        m = GEP_RE.search(line)
        
    # about lines with !dbg (actual source mapped kindoflookups)
        if m and "!dbg" in line:
            res = m.group(1).replace("%", "")
            t = m.group(3) 
            val = m.group(4)
            
    #bound check- if indx >= bound, trap. impoe
            check = f"""
  ; pmc_check_{count}
  %pmc.cmp.{count} = icmp uge {t} {val}, {b}
  br i1 %pmc.cmp.{count}, label %pmc.trap.{count}, label %pmc.safe.{count}

pmc.trap.{count}:
  call void @llvm.trap()
  unreachable

pmc.safe.{count}:"""
            
            out.append(check)
            out.append(line)
            
            needs_trap_decl = True
            count += 1
            print(f"[*] patched %{res} (index type: {t})")
        else:
            out.append(line)

                   # append trap decl to the end of the file if we actually used it
    if needs_trap_decl and "declare void @llvm.trap()" not in ll_data:
        out.append("\n; pmc runtime support\ndeclare void @llvm.trap()")

    return '\n'.join(out)
          #main223
def main():
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <bound>")
        sys.exit(1)
        
    bound = sys.argv[1]
    
    try:
        with open("unified.ll", "r") as f:
            raw = f.read()
            #better inside printlns thans py prints
        print(f"[*] instrumenting unified.ll with bound {bound}...")
        
        fixed = inject_checks(raw, bound)
        
        with open("unified_hardened.ll", "w") as f:
            f.write(fixed)
            
        print(f"[+] build success: {bound} items protected.")
        
    except FileNotFoundError:
        print("[!] error: unified.ll not found")
        sys.exit(1)
    except Exception as e:
        print(f"[!] crash: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
        
        
        
        
        
        
        
        
        
        
        
