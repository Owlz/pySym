import logging
import z3
import ast
import pyState
from pyObjectManager.Int import Int
from pyObjectManager.Real import Real
from pyObjectManager.BitVec import BitVec
from copy import deepcopy

logger = logging.getLogger("pyState:UnaryOp")

def handle(state,element,ctx=None):
    """
    Input:
        state = State object
        element = ast.UnaryOp element to parse
        (optional) ctx = context to resolve UnaryOp in if not current
    Action:
        Parse out the element with respect to the state
    Returns:
        pyObjectManager object representing this UnaryOp
    """
    ctx = state.ctx if ctx is None else ctx
    
    assert type(state) == pyState.State
    assert type(element) == ast.UnaryOp

    op = element.op
    target = state.resolveObject(element.operand)
    
    if type(target) not in [Int, Real, BitVec]:
        err = "handle: unable to resolve UnaryOp target type '{0}'".format(type(target))
        logger.error(err)
        raise Exception(err)
    
    # Get a new variable
    t,args = pyState.duplicateSort(target)
    newVar = state.getVar("tempUnaryOp",varType=t,kwargs=args)
    newVar.increment()
    
    if type(op) == ast.USub:
        state.addConstraint(newVar.getZ3Object() == -target.getZ3Object())

    elif type(op) == ast.UAdd:
        state.addConstraint(newVar.getZ3Object() == target.getZ3Object())

    elif type(op) == ast.Not:
        state.addConstraint(newVar.getZ3Object() == z3.Not(target.getZ3Object()))

    elif type(op) == ast.Invert:
        err = "handle: Invert not implemented yet"
        logger.error(err)
        raise Exception(err)

    else:
        # We really shouldn't get here...
        err = "handle: {0} not implemented yet".format(type(op))
        logger.error(err)
        raise Exception(err)

    return newVar.copy()
