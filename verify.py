#!/usr/bin/env python3
import sys
import re
import z3
import llvmlite.binding as llvm

def resolve_val(val_str, sigma):
    if val_str in sigma:
        return sigma[val_str]
    try:
        return z3.BitVecVal(int(val_str), 32)
    except ValueError:
        return z3.BitVec(val_str, 32)

def extract_operands(instr):
    s = str(instr).split('!dbg')[0]
    try:
        parts = s.split('add')[-1].split(',')
        return parts[0].strip().split()[-1], parts[1].strip()
    except:
        return None, None

def translate_to_z3_logic(instr, sigma):
    # strip metadata nodes before translation
    s = str(instr).split('!dbg')[0]
    try:
        condition = s.split('icmp ')[-1].strip().split(' ')[0]
        ops = s.split(',')
        v1 = resolve_val(ops[0].strip().split()[-1], sigma)
        v2 = resolve_val(ops[1].strip(), sigma)

        if condition == 'slt': return v1 < v2
        if condition == 'sgt': return v1 > v2
        if condition == 'sle': return v1 <= v2
        if condition == 'sge': return v1 >= v2
        if condition == 'eq':  return v1 == v2
        if condition == 'ne':  return v1 != v2
        return v1 == v2 
    except:
        return None

def extract_gep_index(instr):
    s = str(instr).split('!dbg')[0]
    try:
        return s.split(',')[-1].strip().split()[-1]
    except:
        return None

def get_source_line(instr_str, ir_code):
    dbg_match = re.search(r'!dbg !(\d+)', instr_str)
    if dbg_match:
        dbg_id = dbg_match.group(1)
        loc_match = re.search(rf'!{dbg_id}\s*=\s*!DILocation\(line:\s*(\d+),\s*column:\s*(\d+)', ir_code)
        if loc_match:
            return loc_match.group(1), loc_match.group(2)
    return "?", "?"

def extract_bounds_from_ir_metadata(ir_string):
    lengths = re.findall(r'\[(\d+)\s*x\s*i8\]', ir_string)
    if lengths:
        max_bytes = max(int(l) for l in lengths)
        discovered_length = max_bytes // 4
        print(f"z3_scan: resolved dyn_bound={discovered_length}")
        return discovered_length
    return 0

def is_user_function(func_name):
    ignore_prefixes = ['llvm.', 'runtime.', 'fmt.', 'os.', 'syscall.', 'main.init', 'C.']
    for prefix in ignore_prefixes:
        if func_name.startswith(prefix):
            return False
    return True

def verify_polyglot_bounds(ir_file_path, original_filepath):
    solver = z3.Solver()
    sigma = {} 
    path_condition = z3.BoolVal(True) 
    
    with open(ir_file_path, 'r') as f:
        ir_string = f.read()
        
    try:
        module = llvm.parse_assembly(ir_string)
    except Exception as e:
        sys.stderr.write("fatal: llvm.parse_assembly failed\n")
        sys.exit(1)

    dynamic_ir_bound = extract_bounds_from_ir_metadata(ir_string)

    for function in module.functions:
        if not is_user_function(function.name):
            continue

        for block in function.blocks:
            for instr in block.instructions:
                if instr.opcode == 'add':
                    op1, op2 = extract_operands(instr)
                    if op1 and op2:
                        sigma[instr.name] = sigma.get(op1, resolve_val(op1, sigma)) + \
                                           sigma.get(op2, resolve_val(op2, sigma))
                
                elif instr.opcode == 'icmp':
                    condition_expr = translate_to_z3_logic(instr, sigma)
                    if condition_expr is not None:
                        path_condition = z3.And(path_condition, condition_expr)
                
                elif instr.opcode == 'getelementptr':
                    instr_str = str(instr)
                    if "i32, ptr" not in instr_str or "!dbg" not in instr_str:
                        continue

                    index_var = extract_gep_index(instr)
                    if not index_var: continue
                    
                    sym_index = resolve_val(index_var, sigma)
                    
                    if z3.is_bv_value(sym_index):
                        val = sym_index.as_signed_long()
                        if val < -10000 or val > 10000:
                            continue
                    
                    safety_prop = z3.And(sym_index >= 0, sym_index < dynamic_ir_bound)
                    query = z3.And(path_condition, z3.Not(safety_prop))
                    
                    solver.push() 
                    solver.add(query)
                    
                    if solver.check() == z3.sat:
                        model = solver.model()
                        broken_val = model.eval(sym_index)
                        line, col = get_source_line(instr_str, ir_string)
                        emit_diagnostic(line, col, broken_val, dynamic_ir_bound, original_filepath)
                        sys.exit(1) 
                    
                    solver.pop() 
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    verify_polyglot_bounds(sys.argv[1], sys.argv[2])
