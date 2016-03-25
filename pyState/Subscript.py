import logging
import z3
import ast
import pyState
from pyObjectManager.Int import Int
from pyObjectManager.Real import Real
from pyObjectManager.BitVec import BitVec
from pyObjectManager.List import List
from copy import deepcopy

logger = logging.getLogger("pyState:Subscript")

def _handleIndex(state,sub_object,sub_slice):

    if type(sub_object) is not List:
        err = "handleIndex: Don't know how to subscript type {0}".format(sub_object)
        logger.error(err)
        raise Exception(err)

    # Resolve the index value
    sub_index = state.resolveObject(sub_slice.value)

    if sub_index.isStatic():
        index = sub_index.getZ3Object().as_long()

    # Check if it's a variable that only has one possibility
    elif type(sub_index) in [Int, BitVec] and len(state.any_n_int(sub_index,2)) == 1:
        index = state.any_int(sub_index)

    else:
        err = "handle: Don't know how to handle symbolic slice integers at the moment"
        logger.error(err)
        raise Exception(err)

    return sub_object[index]


def handle(state,element,ctx=None):
    """
    Input:
        state = State object
        element = ast.Subscript element to parse
        (optional) ctx = context to resolve subscript in if not current
    Action:
        Parse out the subscript. Return element type expected. If this is an
        index, that means the element itself. If it's a range, that means a list
    Returns:
        Subscript resolved element (optionally as (element, parent))
    """
    ctx = state.ctx if ctx is None else ctx
    
    assert type(state) == pyState.State
    assert type(element) == ast.Subscript

    sub_slice = element.slice
    sub_value = element.value

    if type(sub_value) not in [ast.Name,ast.Subscript]:
        err = "handle: Don't know how to handle value type {0}".format(sub_value)
        logger.error(err)
        raise Exception(err)

    sub_object = state.resolveObject(sub_value,ctx=ctx)

    if type(sub_slice) is ast.Index:
        return _handleIndex(state,sub_object,sub_slice)

    else:
        err = "handle: Don't know how to handle slice type {0}".format(sub_slice)
        logger.error(err)
        raise Exception(err)

