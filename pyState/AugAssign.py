import logging
import z3
import ast
from pyState import hasRealComponent, ReturnObject, z3Helpers
import pyState.z3Helpers
from pyObjectManager.Int import Int
from pyObjectManager.Real import Real
from pyObjectManager.BitVec import BitVec


logger = logging.getLogger("pyState:AugAssign")

def handle(state,element):
    """
    Attempt to handle the AugAssign element
    Example of this: x += 1
    """
    # TODO: Revisit this implimentation. I think I can make this a lot better now.
    
    # Targets are what is being set
    target = element.target

    # Value is what to set them to
    value = element.value

    # The operations to do (Add/Mul/etc)
    op = element.op    

    # Only know how to handle name types
    if type(target) == ast.Name:
        # Grab the var name
        target = target.id
    
    else:
        err = "Don't know how to handle target type {0} at line {1} col {2}".format(type(target),target.lineno,target.col_offset)
        logger.error(err)
        raise Exception(err)

    # Figure out value type
    if type(value) in [ast.Num,ast.Name,ast.Call,ReturnObject,ast.BinOp]:
        value = state.resolveObject(value)
        
        # Check if we're making a call and need to wait for that to finish
        if type(value) == ReturnObject:
            return [state]

        if type(value) in [Int, Real, BitVec]:
            value = value.getZ3Object()

    elif type(value) == ast.Name:
        #value = state.getZ3Var(value.id)
        #value = state.objectManager.getZ3Var(value.id,ctx=state.ctx)
        value = state.objectManager.getVar(value.id,ctx=state.ctx).getZ3Object()

    else:
        err = "Don't know how to handle value type {0} at line {1} col {2}".format(type(value),value.lineno,value.col_offset)
        logger.error(err)
        raise Exception(err)
    
    # Basic sanity checks complete. For augment assigns we will always need to update the vars.
    # Grab the old var and create a new now
    #oldTargetVar = state.getZ3Var(target)
    #oldTargetVar = state.objectManager.getZ3Var(target,ctx=state.ctx)
    oldTargetVar = state.objectManager.getVar(target,ctx=state.ctx).getZ3Object()

    # Match up the right hand side
    oldTargetVar, value = z3Helpers.z3_matchLeftAndRight(oldTargetVar,value,op)
    
    # Z3 gets confused if we don't change our var to Real when comparing w/ Real
    if hasRealComponent(value):
        #newTargetVar = state.getZ3Var(target,increment=True,varType=z3.RealSort())
        #newTargetVar = state.objectManager.getZ3Var(target,increment=True,varType=z3.RealSort(),ctx=state.ctx)
        newTargetVar = state.objectManager.getVar(target,ctx=state.ctx,varType=Real).getZ3Object(increment=True)
    elif type(value) is z3.BitVecRef:
        #newTargetVar = state.getZ3Var(target,increment=True,varType=z3.BitVecSort(value.size()))
        newTargetVar = state.objectManager.getVar(target,ctx=state.ctx,varType=BitVec,kwargs={'size':value.size()}).getZ3Object(increment=True)
    else:
        #newTargetVar = state.getZ3Var(target,increment=True)
        #newTargetVar = state.objectManager.getZ3Var(target,increment=True,ctx=state.ctx)
        newTargetVar = state.objectManager.getVar(target,ctx=state.ctx).getZ3Object(increment=True)

    # Figure out what the op is and add constraint
    if type(op) == ast.Add:
        if type(newTargetVar) in [z3.BitVecRef, z3.BitVecNumRef]:
            # Check for over and underflows
            state.solver.add(pyState.z3Helpers.bvadd_safe(oldTargetVar,value))
        state.addConstraint(newTargetVar == oldTargetVar + value)
    
    elif type(op) == ast.Sub:
        if type(newTargetVar) in [z3.BitVecRef, z3.BitVecNumRef]:
            # Check for over and underflows
            state.solver.add(pyState.z3Helpers.bvsub_safe(oldTargetVar,value))
        state.addConstraint(newTargetVar == oldTargetVar - value)

    elif type(op) == ast.Mult:
        if type(newTargetVar) in [z3.BitVecRef, z3.BitVecNumRef]:
            # Check for over and underflows
            state.solver.add(pyState.z3Helpers.bvmul_safe(oldTargetVar,value))
        state.addConstraint(newTargetVar == oldTargetVar * value)
    
    elif type(op) == ast.Div:
        if type(newTargetVar) in [z3.BitVecRef, z3.BitVecNumRef]:
            # Check for over and underflows
            state.solver.add(pyState.z3Helpers.bvdiv_safe(oldTargetVar,value))
        state.addConstraint(newTargetVar == oldTargetVar / value)
    
    elif type(op) == ast.Mod:
        state.addConstraint(newTargetVar == oldTargetVar % value)

    elif type(op) == ast.BitXor:
        logger.debug("{0} = {1} ^ {2}".format(newTargetVar.size(),oldTargetVar.size(),value.size()))
        state.addConstraint(newTargetVar == oldTargetVar ^ value)

    elif type(op) == ast.BitOr:
        state.addConstraint(newTargetVar == oldTargetVar | value)

    elif type(op) == ast.BitAnd:
        state.addConstraint(newTargetVar == oldTargetVar & value)
    
    elif type(op) == ast.LShift:
        state.addConstraint(newTargetVar == oldTargetVar << value)

    elif type(op) == ast.RShift:
        state.addConstraint(newTargetVar == oldTargetVar >> value)

    # TODO: This will fail with BitVec objects...
    elif type(op) == ast.Pow:
        state.addConstraint(newTargetVar == oldTargetVar ** value)

    else:
        err = "Don't know how to handle op type {0} at line {1} col {2}".format(type(op),op.lineno,op.col_offset)
        logger.error(err)
        raise Exception(err)

    # Pop the instruction off
    state.path.pop(0)
    
    # Return the state
    return [state]
