import logging
import z3
import ast
import pyState.Compare
from copy import deepcopy

logger = logging.getLogger("pyState:While")

def _handle(stateIf,stateElse,element,ifConstraint):

    # Add the constraints
    stateIf.addConstraint(ifConstraint)
    stateElse.addConstraint(z3.Not(ifConstraint))

    # Check if statement. We'll have at least one instruction here, so treat this as a call
    # Saving off the current path so we can return to it and pick up at the next instruction
    cs = deepcopy(stateIf.path)
    # Only push our stack if it's not empty
    if len(cs) > 0:
        stateIf.pushCallStack(path=cs)

    # Our new path becomes the inside of the if statement
    stateIf.path = element.body

    # If state should get a copy of the loop we're now in
    stateIf.loop = deepcopy(element)

    # Update the else's path
    # Check if there is an else path we need to take
    #if len(element.orelse) > 0:
    cs = deepcopy(stateElse.path)
    if len(cs) > 0:
        stateElse.pushCallStack(path=cs)

    # else side should be done with the loop
    stateElse.loop = None

    stateElse.path = element.orelse

    return [stateIf, stateElse]


def handle(state,element):
    """
    Attempt to handle the while element
    """
    
    # While is basically a repeated If statement, we want to take both sides

    stateIf = state
    ret = []

    # Check what type of test this is    
    if type(element.test) == ast.Compare:
        # Try to handle the compare
        ifConstraint = pyState.Compare.handle(stateIf,element.test)

    else:
        err = "handle: I don't know how to handle type {0}".format(type(element.test))
        logger.error(err)
        raise Exception(err)

    # Normalize
    ifConstraint = ifConstraint if type(ifConstraint) is list else [ifConstraint]

    # See if we need to pass back a call
    retObjs = [x.state for x in ifConstraint if type(x) is pyState.ReturnObject]
    if len(retObjs) > 0:
        return retObjs

    # If we're good to go, pop the instruction
    stateIf.path.pop(0)

    # Loop through possible constraints
    for constraint in ifConstraint:
        
        ret += _handle(stateIf.copy(),stateIf.copy(),element,constraint)

    return ret
