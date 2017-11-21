import logging
from pySym.pyObjectManager.List import List
from pySym.pyObjectManager.Int import Int
from pySym.pyObjectManager.Real import Real
from pySym.pyObjectManager.BitVec import BitVec
from pySym.pyObjectManager.Char import Char
from pySym.pyObjectManager.String import String
import ast
from pySym import pyState

logger = logging.getLogger("pyState:SimFunction:String.join")


def handle(state,call,elem,ctx=None):
    """
    Simulate Python's join string method
    """
    ctx = ctx if ctx is not None else state.ctx

    # The root (i.e.: "s" in s.join())
    root = state.resolveObject(call.func.value,ctx=ctx)

    assert len(root) == 1
    root = root.pop()

    assert type(root) is String

    # Resolve the elem
    elems = state.resolveObject(elem,ctx=ctx)

    elems = elems if type(elems) is list else [elems]

    # If we're waiting on a symbolic call, return
    retObjs = [x for x in elems if type(x) is pyState.ReturnObject]
    if len(retObjs) > 0:
        return retObjs

    ret = []

    for elem in elems:

        if type(elem) is not List:
            err = "handle: Don't know how to handle non-List join iterators"
            logger.error(err)
            raise Exception(err)

    
        # Get new string
        newString = state.getVar('tempStrJoin',ctx=1,varType=String)
        newString.increment()

        # Loop through elem values
        for item in elem:
            if type(item) is String:
                newString.variables += item.variables + root.variables
            elif type(item) is Char:
                newString.variables += [item.variable] + root.variables
            else:
                err = "handle: Don't know how to handle type {0}".format(type(item))
                logger.error(err)
                raise Exception(err)

        if root.length() > 0:
            # Remove the excess chars that may have built up
            newString = newString[:-root.length()]
    
        ret.append(newString.copy())

    return ret

