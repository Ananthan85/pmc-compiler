#!/usr/bin/env python3
"""
LLVM IR Bounds Checking Pass
Parses intermediate representation and injects runtime bounds checks
for array access instructions to enforce memory safety.
"""

import sys
import re
import logging
from typing import List

# Configure standard logging for build output
logging.basicConfig(level=logging.INFO, format="[IR-Pass] %(message)s")

# Regex to match getelementptr operations specifically targeting 32-bit integer arrays
# Extracts: (1) Result Register, (2) Base Pointer, (3) Index Type, (4) Index Value
GEP_PATTERN = re.compile(
    r'(\%\w+)\s*=\s*getelementptr inbounds i32, ptr\s*(\%\w+),\s*(i32|i64)\s*(\%\w+|\d+)'
)

def inject_runtime_checks(ir_string: str, bound: str) -> str:
    """
    Scans the raw LLVM IR string and injects comparison and trap 
    instructions prior to memory accesses.
    """
    lines: List[str] = ir_string.split('\n')
    instrumented_lines: List[str] = []
    
    trap_injected: bool = False
    counter: int = 0

    for line in lines:
        # Check for target instructions that include debug metadata
        match = GEP_PATTERN.search(line)
        
        if match and "!dbg" in line:
            result_reg: str = match.group(1).replace("%", "")
            index_type: str = match.group(3) 
            index_val: str = match.group(4)
            
            # Construct the bounds check basic blocks
            injection = (
                f"\n  ; <pmc_chk_bounds>\n"
                f"  %pmc.cmp.{counter} = icmp uge {index_type} {index_val}, {bound}\n"
                f"  br i1 %pmc.cmp.{counter}, label %pmc.trap.{counter}, label %pmc.safe.{counter}\n\n"
                f"pmc.trap.{counter}:\n"
                f"  call void @llvm.trap()\n"
                f"  unreachable\n\n"
                f"pmc.safe.{counter}:"
            )
            
            instrumented_lines.append(injection)
            instrumented_lines.append(line)
            
            trap_injected = True
            counter += 1
            
            logging.info(f"opt_bounds: Injected {index_type} trap at register %{result_reg}")
        else:
            # Pass through non-matching IR untouched
            instrumented_lines.append(line)

    # ---> FIXED: This is now OUTSIDE the for loop <---
    # Append the trap declaration at the global level if it's missing
    if trap_injected and "declare void @llvm.trap()" not in ir_string:
        instrumented_lines.append("\n; Runtime trap declaration for bounds failures")
        instrumented_lines.append("declare void @llvm.trap()")

    return '\n'.join(instrumented_lines)


def main() -> int:
    """Main execution entry point."""
    if len(sys.argv) < 2:
        logging.error("Missing bounds argument. Usage: ./instrument.py <bound>")
        return 1
        
    bound_limit: str = sys.argv[1]
    input_file: str = "unified.ll"
    output_file: str = "unified_hardened.ll"
    
    try:
        with open(input_file, "r") as f:
            raw_ir: str = f.read()
            
        logging.info(f"Loaded '{input_file}'. Starting instrumentation pass...")
        
        hardened_ir: str = inject_runtime_checks(raw_ir, bound_limit)
        
        with open(output_file, "w") as f:
            f.write(hardened_ir)
            
        logging.info(f"Instrumentation complete. Hardened IR written to '{output_file}'.")
        return 0
        
    except FileNotFoundError:
        logging.error(f"Could not locate input file: {input_file}")
        return 1
    except Exception as e:
        logging.error(f"An unexpected exception occurred during instrumentation: {e}")
        return 1

if __name__ == "__main__":
    # Execute main and pass the return code to the OS
    sys.exit(main())
        
        
        
        
        
        
        
        
        
        
        
        
