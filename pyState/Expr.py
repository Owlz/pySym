import logging
import z3
import ast
import pyState
from . import Call, ReturnObject

logger = logging.getLogger("pyState:Expr")

def handle(state,element):
    """
    Input:
        state = State object
        element = ast.Expr element to parse
    Action:
        Figure out what to do with this...
    Returns:
        Nothing?
    """
    
    assert type(state) == pyState.State
    assert type(element) == ast.Expr

    # What is this expression?
    value = element.value

    if type(value) == ast.Call:
        ret = state.resolveObject(value)
        
        # Normalize
        ret = [ret] if type(ret) is not list else ret

        # Check for return object. Return all applicable
        retObjs = [x.state for x in ret if type(x) is pyState.ReturnObject]
        if len(retObjs) > 0:
            return retObjs

        states = [x for x in ret if type(x) is pyState.State]
        
        if len(states) > 0:
            return states

    # Don't really care about the return object for now... Maybe later?
    elif type(value) == ReturnObject:
        pass

    else:
        err = "Expr: Don't know how to handle expr type {0} at line {1} col {2}".format(type(value),value.lineno,value.col_offset)
        logger.error(err)
        raise Exception(err)
    

    state.path.pop(0)
    return [state]

