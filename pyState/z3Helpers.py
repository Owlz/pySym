"""
A file to hold my helper items directly relating to z3
"""

import z3
import ast
import pyState
import logging

logger = logging.getLogger("pyState:z3Helpers")

Z3_DEFAULT_BITVEC_SIZE = 64

#############################
# Watch for BitVec Overflow #
#############################

def bvadd_safe(x, y, signed=False):
    assert x.ctx_ref()==y.ctx_ref()
    a, b = z3._coerce_exprs(x, y)
    return (z3.BoolRef(z3.Z3_mk_bvadd_no_overflow(a.ctx_ref(), a.as_ast(), b.as_ast(), signed)),
            z3.BoolRef(z3.Z3_mk_bvadd_no_underflow(a.ctx_ref(), a.as_ast(), b.as_ast())))

def bvmul_safe(x, y, signed=False):
    assert x.ctx_ref()==y.ctx_ref()
    a, b = z3._coerce_exprs(x, y)
    return (z3.BoolRef(z3.Z3_mk_bvmul_no_overflow(a.ctx_ref(), a.as_ast(), b.as_ast(), signed)),
            z3.BoolRef(z3.Z3_mk_bvmul_no_underflow(a.ctx_ref(), a.as_ast(), b.as_ast())))

def bvsub_safe(x, y, signed=False):
    assert x.ctx_ref()==y.ctx_ref()
    a, b = z3._coerce_exprs(x, y)
    return (z3.BoolRef(z3.Z3_mk_bvsub_no_overflow(a.ctx_ref(), a.as_ast(), b.as_ast())),
            z3.BoolRef(z3.Z3_mk_bvsub_no_underflow(a.ctx_ref(), a.as_ast(), b.as_ast(), signed)))

def bvdiv_safe(x, y, signed=False):
    assert x.ctx_ref()==y.ctx_ref()
    a, b = z3._coerce_exprs(x, y)
    return z3.BoolRef(z3.Z3_mk_bvsdiv_no_overflow(a.ctx_ref(), a.as_ast(), b.as_ast()))


def z3_bv_to_int(x):
    # Convers BitVec to Int in the solver
    # example: s.add(q == to_int(z)) where q == IntSort and z == BitVecSort
    return z3.ArithRef(z3.Z3_mk_bv2int(x.ctx_ref(), x.as_ast(), 0), x.ctx)

def z3_int_to_bv(x,size=Z3_DEFAULT_BITVEC_SIZE):
    assert type(x) in [z3.IntNumRef,z3.ArithRef]
    assert x.is_int()
    # Converts Int to BV
    return z3.BitVecRef(z3.Z3_mk_int2bv(x.ctx_ref(),size,x.as_ast()))


def isZ3Object(obj):
    """
    Determine if the object given is a z3 type object
    """
    if type(obj) in [z3.ArithRef, z3.IntNumRef, z3.RatNumRef, z3.BitVecRef, z3.BitVecNumRef, z3.ArrayRef, z3.SeqRef]:
        return True
    return False

def mk_var(name,vsort):
    if vsort.kind() == z3.Z3_INT_SORT:
        v = z3.Int(name)
    elif vsort.kind() == z3.Z3_REAL_SORT:
        v = z3.Real(name)
    elif vsort.kind() == z3.Z3_BOOL_SORT:
        v = z3.Bool(name)
    elif vsort.kind() == z3.Z3_DATATYPE_SORT:
        v = z3.Const(name,vsort)
    elif vsort.kind() == z3.Z3_BV_SORT:
        v = z3.BitVec(name,vsort.size())

    else:
        assert False, 'Cannot handle this sort (s: %sid: %d)'\
            %(vsort,vsort.kind())

    return v

def z3_matchLeftAndRight(left,right,op):
    """
    Input:
        left = z3 object
        right = z3 object
        op = ast operation that will be performed
    Action:
        Appropriately cast the two variables so that they can be used in an expression
        Main problem is between Int type and BitVec type
    Returns:
        (left,right) where both vars should be able to be used together
    """
    lType = type(left)
    rType = type(right)

    logger.debug("z3_matchLeftAndRight: Called to match {0} and {1}".format(type(left),type(right)))
    needBitVec = True if type(op) in [ast.BitXor, ast.BitAnd, ast.BitOr, ast.LShift, ast.RShift] else False
    # TODO: If the two sizes are different, we'll have problems down the road.
    bitVecSize = max([c.size() for c in [b for b in [left,right] if type(b) in [z3.BitVecRef, z3.BitVecNumRef]]],default=Z3_DEFAULT_BITVEC_SIZE)

    #####################################
    # Case: Both are already BitVectors #
    #####################################
    # Check length. Extend if needed.
    if type(left) in [z3.BitVecRef, z3.BitVecNumRef] and type(right) in [z3.BitVecRef, z3.BitVecNumRef]:
        logger.debug("z3_matchLeftAndRight: Matching BitVecLength @ {0} (left={1},right={2})".format(bitVecSize,left.size(),right.size()))
        if left.size() < right.size():
            # Sign extend left's value to match
            left = z3.SignExt(right.size()-left.size(),left)
        elif right.size() > left.size():
            right = z3.SignExt(left.size()-right.size(),right)
        
        return left,right

    #####################################
    # Case: One is BitVec and one isn't #
    #####################################
    # For now only handling casting of int to BV. Not other way around.
    if (lType in [z3.BitVecNumRef, z3.BitVecRef] and rType in [z3.ArithRef,z3.IntNumRef]) or (rType in [z3.ArithRef,z3.IntNumRef] and needBitVec):
        # If we need to convert to BitVec and it is a constant, not variable, do so more directly
        if rType is z3.IntNumRef and right.is_int():
            right = z3.BitVecVal(right.as_long(),bitVecSize)
        # Otherwise cast it. Not optimal, but oh well.
        else:
            right = z3_int_to_bv(right,size=bitVecSize)

    if (rType in [z3.BitVecNumRef, z3.BitVecRef] and lType in [z3.ArithRef,z3.IntNumRef]) or (lType in [z3.ArithRef,z3.IntNumRef] and needBitVec):
        if lType is z3.IntNumRef and left.is_int():
            left = z3.BitVecVal(left.as_long(),bitVecSize)
        else:
            left = z3_int_to_bv(left,size=bitVecSize)
    
    logger.debug("z3_matchLeftAndRight: Returning {0} and {1}".format(type(left),type(right)))

    return (left,right)

